"""Register release approval and permit an invalidated review to be retried."""

from erev_api.db import migration_ops as ops

revision = "0169"
down_revision = "0168"
branch_labels = None
depends_on = None

BEFORE = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['processing_seed', 'accepted_attempt_id', 'enabled_at', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.accepted_attempt_id IS NOT NULL AND NEW.accepted_attempt_id IS DISTINCT FROM OLD.accepted_attempt_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: accepted_attempt_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.enabled_at IS NOT NULL AND NEW.enabled_at IS DISTINCT FROM OLD.enabled_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: enabled_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['INCOMPLETE>RUNNING', 'PENDING>RUNNING', 'PENDING_APPROVAL>APPROVED', 'PENDING_APPROVAL>REJECTED', 'RUNNING>FAILED', 'RUNNING>INCOMPLETE', 'RUNNING>PASSED', 'RUNNING>PENDING_APPROVAL']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  IF OLD.processing_seed IS NOT NULL AND NEW.processing_seed IS DISTINCT FROM OLD.processing_seed THEN
    RAISE EXCEPTION 'Processing seed is already set' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

AFTER = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['processing_seed', 'accepted_attempt_id', 'enabled_at', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.accepted_attempt_id IS NOT NULL AND NEW.accepted_attempt_id IS DISTINCT FROM OLD.accepted_attempt_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: accepted_attempt_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.enabled_at IS NOT NULL AND NEW.enabled_at IS DISTINCT FROM OLD.enabled_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: enabled_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['INCOMPLETE>RUNNING', 'PENDING>RUNNING', 'PENDING_APPROVAL>APPROVED', 'PENDING_APPROVAL>INCOMPLETE', 'PENDING_APPROVAL>REJECTED', 'RUNNING>FAILED', 'RUNNING>INCOMPLETE', 'RUNNING>PASSED', 'RUNNING>PENDING_APPROVAL']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  IF OLD.processing_seed IS NOT NULL AND NEW.processing_seed IS DISTINCT FROM OLD.processing_seed THEN
    RAISE EXCEPTION 'Processing seed is already set' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def _replace(body: str) -> None:
    ops.execute(
        "CREATE OR REPLACE FUNCTION erev.tg_release_validation__transition() "
        "RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER "
        "SET search_path = erev, pg_catalog AS $fn$" + body + "$fn$"
    )


def _report_filter(add: bool) -> None:
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET parameters_schema = jsonb_set(parameters_schema, "
        "'{properties,subject_types,items,enum}', "
        "(parameters_schema #> '{properties,subject_types,items,enum}') "
        "|| '\"ENGINE_RELEASE_VALIDATION\"'::jsonb) "
        "WHERE code = 'approvals_register' AND version = 1"
        if add
        else "UPDATE erev.report_definition SET parameters_schema = jsonb_set(parameters_schema, "
        "'{properties,subject_types,items,enum}', "
        "(parameters_schema #> '{properties,subject_types,items,enum}') "
        "- 'ENGINE_RELEASE_VALIDATION') "
        "WHERE code = 'approvals_register' AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    ops.add_enum_value("approval_subject_type", "ENGINE_RELEASE_VALIDATION")
    _replace(AFTER)
    _report_filter(True)


def downgrade() -> None:
    ops.remove_enum_value("approval_subject_type", "ENGINE_RELEASE_VALIDATION")
    _report_filter(False)
    _replace(BEFORE)
