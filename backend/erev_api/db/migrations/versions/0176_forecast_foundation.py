"""Persist forecast scenarios, versioned inputs, runs and deal previews (FCS foundation).

No forecast execution or production posting is enabled by this revision.
"""

import sqlalchemy as sa
from erev_api.db import migration_ops as ops
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "0176"
down_revision = "0175"
branch_labels = None
depends_on = None

FORECAST_RUN_TRANSITION_BODY = """
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
   WHERE n.key <> ALL (ARRAY['finished_at', 'problem', 'report_run_ids', 'row_version', 'started_at', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
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
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['QUEUED>FAILED', 'QUEUED>RUNNING', 'RUNNING>FAILED', 'RUNNING>SUCCEEDED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

DEAL_PREVIEW_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['saved_contract_id']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.saved_contract_id IS NOT NULL AND NEW.saved_contract_id IS DISTINCT FROM OLD.saved_contract_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: saved_contract_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

SCENARIO_GUARD = """
BEGIN
  IF NOT EXISTS (SELECT 1 FROM erev.tenant WHERE id = NEW.tenant_id AND kind = 'production')
     OR NOT EXISTS (SELECT 1 FROM erev.tenant WHERE id = NEW.scenario_tenant_id
       AND kind = 'sandbox' AND source_tenant_id = NEW.tenant_id) THEN
    RAISE EXCEPTION 'Scenario must link production to its own sandbox' USING ERRCODE = '23514';
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.scenario_tenant_id IS DISTINCT FROM OLD.scenario_tenant_id THEN
    RAISE EXCEPTION 'Scenario tenant is immutable' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
"""
SANDBOX_GUARD = """
BEGIN
  IF NOT EXISTS (SELECT 1 FROM erev.tenant WHERE id = NEW.tenant_id AND kind = 'sandbox') THEN
    RAISE EXCEPTION 'Forecast inputs and runs require a sandbox' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
"""
PREVIEW_GUARD = """
BEGIN
  IF NEW.saved_contract_id IS NOT NULL AND NOT EXISTS
     (SELECT 1 FROM erev.tenant WHERE id = NEW.tenant_id AND kind = 'sandbox') THEN
    RAISE EXCEPTION 'DEAL_PREVIEW_SAVE_NOT_ALLOWED' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
"""


def upgrade() -> None:
    ops.create_enum("scenario_status", ("ACTIVE", "ARCHIVED"))
    ops.create_tenant_table(
        "scenario",
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("purpose", ops.NamedType("erev.memo")),
        sa.Column("scenario_tenant_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("base_known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            ops.NamedType("erev.scenario_status"),
            nullable=False,
            server_default=sa.text("'ACTIVE'"),
        ),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True)),
        standard_sets=["SC-C", "SC-M"],
        unique=[("ux_scenario__tenant", ["tenant_id", "scenario_tenant_id"], None)],
    )
    ops.add_global_fk("scenario", "scenario_tenant_id", "tenant")
    ops.add_tenant_fk("scenario", "tenant_snapshot_id", "tenant_snapshot")
    ops.apply_class("scenario", "IM-M")
    ops.enable_rls("scenario", "RLS-T")
    ops.create_trigger(
        "scenario", "scope", SCENARIO_GUARD, timing="BEFORE", events="INSERT OR UPDATE"
    )
    ops.create_tenant_table(
        "forecast_event_set",
        sa.Column("code", ops.NamedType("erev.code"), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("production_scenario_id", sa.Uuid(), nullable=False),
        sa.Column(
            "import_upload_ids", ARRAY(sa.Uuid()), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column("api_commands", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        standard_sets=["SC-C", "SC-M", "SC-V"],
        checks=[("ck_forecast_event_set__commands", "jsonb_typeof(api_commands) = 'array'")],
        unique=[("ux_forecast_event_set__version", ["tenant_id", "code", "version_no"], None)],
    )
    ops.apply_class("forecast_event_set", "IM-P")
    ops.enable_rls("forecast_event_set", "RLS-T")
    ops.add_config_version_trigger("forecast_event_set", scope_columns=["code"])
    ops.create_tenant_table(
        "forecast_run",
        sa.Column("forecast_event_set_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            ops.NamedType("erev.run_status"),
            nullable=False,
            server_default=sa.text("'QUEUED'"),
        ),
        sa.Column("parameters", JSONB(), nullable=False),
        sa.Column(
            "report_run_ids", ARRAY(sa.Uuid()), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column("job_id", sa.Uuid()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("problem", JSONB()),
        standard_sets=["SC-C", "SC-M"],
        checks=[("ck_forecast_run__parameters", "jsonb_typeof(parameters) = 'object'")],
    )
    ops.add_tenant_fk("forecast_run", "forecast_event_set_id", "forecast_event_set")
    ops.add_tenant_fk("forecast_run", "job_id", "job")
    ops.apply_class(
        "forecast_run",
        "IM-S",
        update_columns=(
            "status",
            "report_run_ids",
            "started_at",
            "finished_at",
            "problem",
            "updated_at",
            "updated_by",
            "updated_by_kind",
            "row_version",
        ),
    )
    ops.enable_rls("forecast_run", "RLS-T")
    ops.create_trigger(
        "forecast_run", "transition", FORECAST_RUN_TRANSITION_BODY, timing="BEFORE", events="UPDATE"
    )
    for table in ("forecast_event_set", "forecast_run"):
        ops.create_trigger(
            table, "sandbox", SANDBOX_GUARD, timing="BEFORE", events="INSERT OR UPDATE"
        )
    ops.create_tenant_table(
        "deal_preview",
        sa.Column("input", JSONB(), nullable=False),
        sa.Column("input_sha256", ops.NamedType("erev.sha256"), nullable=False),
        sa.Column("result", JSONB(), nullable=False),
        sa.Column("result_sha256", ops.NamedType("erev.sha256"), nullable=False),
        sa.Column("engine_release_id", sa.Uuid(), nullable=False),
        sa.Column("pinned_refs", JSONB(), nullable=False),
        sa.Column("saved_contract_id", sa.Uuid()),
        standard_sets=["SC-C"],
        checks=[
            (
                "ck_deal_preview__objects",
                "jsonb_typeof(input) = 'object' AND jsonb_typeof(result) = 'object' "
                "AND jsonb_typeof(pinned_refs) = 'object'",
            )
        ],
        indexes=[("ix_deal_preview__created", ["tenant_id", "created_at"], None)],
    )
    ops.add_global_fk("deal_preview", "engine_release_id", "engine_release")
    ops.add_tenant_fk("deal_preview", "saved_contract_id", "contract")
    ops.apply_class("deal_preview", "IM-S", update_columns=("saved_contract_id",))
    ops.enable_rls("deal_preview", "RLS-T")
    ops.create_trigger(
        "deal_preview", "transition", DEAL_PREVIEW_TRANSITION_BODY, timing="BEFORE", events="UPDATE"
    )
    ops.create_trigger(
        "deal_preview", "sandbox", PREVIEW_GUARD, timing="BEFORE", events="INSERT OR UPDATE"
    )


def downgrade() -> None:
    ops.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM erev.scenario) OR EXISTS (SELECT 1 FROM erev.forecast_event_set)
        OR EXISTS (SELECT 1 FROM erev.forecast_run) OR EXISTS (SELECT 1 FROM erev.deal_preview) THEN
        RAISE EXCEPTION 'Forecast evidence exists; downgrade refused';
      END IF;
    END $$""")
    for table in ("deal_preview", "forecast_run", "forecast_event_set", "scenario"):
        ops.drop_tenant_table(table)
    ops.drop_enum("scenario_status")
