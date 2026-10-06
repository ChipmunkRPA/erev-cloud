"""frps3b (lane F-RPS; 04 T-RPT-02 rev 1.55; ENGINE_SPEC_B S15-R-24): ``report_run.source_binding``.
04 ids amended: T-RPT-02 ``report_run`` gains ``source_binding`` (jsonb, NULL) — the sources a
LIVE run's build actually consumed (the effective cutoff, the contract-version ids per book, the
grouping labels its row keys used, its output row keys), written once by the REPORT_RUN job at
SUCCEEDED; NULL for an as-locked run (its frozen dataset is its source, S15-R-19) and for every
run created before this revision (unbound: rerun and cell explanation refuse by name; nothing is
backfilled or reconstructed from today's rows). The IM-S class grants UPDATE on listed columns
only (04 §1.5), so the column joins the ``erev_app`` UPDATE grant, and the DB-03 transition
trigger of 0048 enumerates the columns that may change while QUEUED or RUNNING, so its function
body is replaced with ``source_binding`` in that list (``CREATE OR REPLACE`` keeps the trigger and
the grants; NC-18). ``ck_report_run__source_binding`` requires a JSON object when present.
Revision number taken from main's ``versions`` directory at commit time (DG-MIG-12 numbering);
downgrade restores the 0048 body exactly and drops the column (DG-MIG-04). No seed (DG-MIG-07
uninvolved).
"""

from __future__ import annotations

from erev_api.db import migration_ops as ops

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None

TABLE = "erev.report_run"
# The schema's application role (04 §14.2; the session module's APP_ROLE at this revision's
# authoring state) as a literal: a revision reads no live Python constant (DG-MIG-12).
APP_ROLE = "erev_app"
SIGNATURE = "tg_report_run__transition()"

# The 0048 body with ``source_binding`` among the columns that may change while QUEUED or RUNNING.
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
   WHERE n.key <> ALL (ARRAY['child_report_run_ids', 'control_totals', 'disclosure_snapshot_ids', 'finished_at', 'ledger_heads', 'manifest_file_id', 'output_file_id', 'output_sha256', 'problem', 'row_count', 'row_version', 'source_binding', 'started_at', 'status', 'tie_out_results', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
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

# The 0048 body exactly, for downgrade (DG-MIG-04).
TRANSITION_BODY_0048 = """
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
   WHERE n.key <> ALL (ARRAY['child_report_run_ids', 'control_totals', 'disclosure_snapshot_ids', 'finished_at', 'ledger_heads', 'manifest_file_id', 'output_file_id', 'output_sha256', 'problem', 'row_count', 'row_version', 'started_at', 'status', 'tie_out_results', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
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


def _replace_function(body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger (NC-18 attributes)."""
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.{SIGNATURE} RETURNS trigger LANGUAGE plpgsql "
        f"SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def upgrade() -> None:
    ops.execute(f"ALTER TABLE {TABLE} ADD COLUMN source_binding jsonb NULL")
    ops.execute(
        f"ALTER TABLE {TABLE} ADD CONSTRAINT ck_report_run__source_binding "
        "CHECK (source_binding IS NULL OR jsonb_typeof(source_binding) = 'object')"
    )
    ops.execute(f"GRANT UPDATE (source_binding) ON TABLE {TABLE} TO {APP_ROLE}")
    _replace_function(TRANSITION_BODY)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    _replace_function(TRANSITION_BODY_0048)
    ops.execute(f"REVOKE UPDATE (source_binding) ON TABLE {TABLE} FROM {APP_ROLE}")
    ops.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT ck_report_run__source_binding")
    ops.execute(f"ALTER TABLE {TABLE} DROP COLUMN source_binding")
