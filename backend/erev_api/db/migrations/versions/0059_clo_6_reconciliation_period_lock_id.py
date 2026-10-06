"""BUILD_SPEC CLO-6 correction (Codex review R1 / F-CLO Q-12; supervisor ruling D-98 63): T-CLS-06
``reconciliation.period_lock_id`` becomes updatable write-once.

04 ids amended: T-CLS-06 (rev 1.23) lists ``period_lock_id`` among the IM-S updatable columns as a
write-once member — set by the lock certification while NULL and never changed afterwards (a
second write is a refusal, not an overwrite). DB-03 ``tg_reconciliation__transition`` is replaced
with the body ``erev_api.db.transitions.transition_trigger_sql("reconciliation")`` renders after the
rule change (DG-ARC-07 compares the installed function with a fresh rendering), and ``erev_app``
gains ``UPDATE (period_lock_id)`` on the table. ``CREATE OR REPLACE`` keeps the function's grants
and its trigger; no table, column or enumeration is added. The first F-CLO revision (record §19).
"""

from __future__ import annotations

from erev_api.db import migration_ops as ops

# The application role of 04 §1.5 (``erev_api.db.session.APP_ROLE``), spelt as a literal: DG-MIG-12
# keeps a revision's imports to the DDL helpers, so the name is not read from the live module.
APP_ROLE = "erev_app"

revision = "0059"
down_revision = "0058"

TABLE = "reconciliation"
FUNCTION = "tg_reconciliation__transition()"

# 04 T-CLS-06 rev 1.23: the IM-S updatable columns after this revision (0047's list plus
# ``period_lock_id``); SC-M columns follow as in 0047.
UPDATE_COLUMNS = (
    "status",
    "totals",
    "variance_count",
    "unexplained_other_amount",
    "report_run_id",
    "certified_at",
    "period_lock_id",
)

# DB-03: erev_api.db.transitions.transition_trigger_sql("reconciliation") after D-98 63.
TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF OLD.status::text = ANY (ARRAY['CERTIFIED']::text[]) THEN
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
   WHERE n.key <> ALL (ARRAY['certified_at', 'period_lock_id', 'report_run_id', 'row_version', 'status', 'totals', 'unexplained_other_amount', 'updated_at', 'updated_by', 'updated_by_kind', 'variance_count']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.period_lock_id IS NOT NULL AND NEW.period_lock_id IS DISTINCT FROM OLD.period_lock_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: period_lock_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['AUTO_CERTIFIED>CERTIFIED', 'CERTIFIED>REOPENED', 'DRAFT>AUTO_CERTIFIED', 'DRAFT>PREPARED', 'PREPARED>REOPENED', 'PREPARED>REVIEWED', 'REOPENED>DRAFT', 'REVIEWED>CERTIFIED', 'REVIEWED>REOPENED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

# The 0047 body (04 rev 1.2), restored by downgrade().
PREVIOUS_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF OLD.status::text = ANY (ARRAY['CERTIFIED']::text[]) THEN
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
   WHERE n.key <> ALL (ARRAY['certified_at', 'report_run_id', 'row_version', 'status', 'totals', 'unexplained_other_amount', 'updated_at', 'updated_by', 'updated_by_kind', 'variance_count']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['AUTO_CERTIFIED>CERTIFIED', 'CERTIFIED>REOPENED', 'DRAFT>AUTO_CERTIFIED', 'DRAFT>PREPARED', 'PREPARED>REOPENED', 'PREPARED>REVIEWED', 'REOPENED>DRAFT', 'REVIEWED>CERTIFIED', 'REVIEWED>REOPENED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def _replace_function(signature: str, body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger; NC-18 attributes."""
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.{signature} RETURNS trigger LANGUAGE plpgsql "
        f"SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def upgrade() -> None:
    """Grant the write-once column and install the re-rendered DB-03 body."""
    ops.execute(f"GRANT UPDATE (period_lock_id) ON TABLE erev.{TABLE} TO {APP_ROLE}")
    _replace_function(FUNCTION, TRANSITION_BODY)


def downgrade() -> None:
    """Restore the 0047 body and revoke the column grant (DG-MIG-04)."""
    _replace_function(FUNCTION, PREVIOUS_TRANSITION_BODY)
    ops.execute(f"REVOKE UPDATE (period_lock_id) ON TABLE erev.{TABLE} FROM {APP_ROLE}")
