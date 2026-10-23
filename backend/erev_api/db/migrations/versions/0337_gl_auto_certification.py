"""Allow write-once GL certifying-rule evidence when its trial balance is attached."""

from erev_api.db import migration_ops as ops

revision = "0337"
down_revision = "0336"
branch_labels = None
depends_on = None

OLD = """
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
   WHERE n.key <> ALL (ARRAY['certified_at', 'period_lock_id', 'report_run_id', 'row_version', 'source_file_id', 'status', 'sync_run_id', 'totals', 'unexplained_other_amount', 'updated_at', 'updated_by', 'updated_by_kind', 'variance_count']::text[])
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
  IF OLD.source_file_id IS NOT NULL AND NEW.source_file_id IS DISTINCT FROM OLD.source_file_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: source_file_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.sync_run_id IS NOT NULL AND NEW.sync_run_id IS DISTINCT FROM OLD.sync_run_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: sync_run_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['AUTO_CERTIFIED>CERTIFIED', 'CERTIFIED>REOPENED', 'DRAFT>AUTO_CERTIFIED', 'DRAFT>PREPARED', 'PREPARED>REOPENED', 'PREPARED>REVIEWED', 'REVIEWED>CERTIFIED', 'REVIEWED>REOPENED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501
NEW = """
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
   WHERE n.key <> ALL (ARRAY['auto_certify_rule_id', 'auto_certify_rule_set_version_id', 'certified_at', 'period_lock_id', 'report_run_id', 'row_version', 'source_file_id', 'status', 'sync_run_id', 'totals', 'unexplained_other_amount', 'updated_at', 'updated_by', 'updated_by_kind', 'variance_count']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.auto_certify_rule_id IS NOT NULL AND NEW.auto_certify_rule_id IS DISTINCT FROM OLD.auto_certify_rule_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: auto_certify_rule_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.auto_certify_rule_set_version_id IS NOT NULL AND NEW.auto_certify_rule_set_version_id IS DISTINCT FROM OLD.auto_certify_rule_set_version_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: auto_certify_rule_set_version_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.period_lock_id IS NOT NULL AND NEW.period_lock_id IS DISTINCT FROM OLD.period_lock_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: period_lock_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.source_file_id IS NOT NULL AND NEW.source_file_id IS DISTINCT FROM OLD.source_file_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: source_file_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.sync_run_id IS NOT NULL AND NEW.sync_run_id IS DISTINCT FROM OLD.sync_run_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: sync_run_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['AUTO_CERTIFIED>CERTIFIED', 'CERTIFIED>REOPENED', 'DRAFT>AUTO_CERTIFIED', 'DRAFT>PREPARED', 'PREPARED>REOPENED', 'PREPARED>REVIEWED', 'REVIEWED>CERTIFIED', 'REVIEWED>REOPENED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def _replace(body: str) -> None:
    ops.execute(
        "CREATE OR REPLACE FUNCTION erev.tg_reconciliation__transition() "
        "RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER "
        "SET search_path = erev, pg_catalog AS $fn$" + body + "$fn$"
    )


def upgrade() -> None:
    ops.execute(
        "GRANT UPDATE (auto_certify_rule_set_version_id, auto_certify_rule_id) "
        "ON TABLE erev.reconciliation TO erev_app"
    )
    _replace(NEW)


def downgrade() -> None:
    _replace(OLD)
    ops.execute(
        "REVOKE UPDATE (auto_certify_rule_set_version_id, auto_certify_rule_id) "
        "ON TABLE erev.reconciliation FROM erev_app"
    )
