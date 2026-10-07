"""Require fresh task signoffs after reopen; retain historical signoff rows.

The task signature hash binds its close cycle. Other signoff subjects retain their uniqueness.
Downgrade refuses repeated historical signatures rather than discarding evidence.
"""

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0135"
down_revision = "0134"
branch_labels = None
depends_on = None

BODY: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['comment', 'control_execution_id', 'due_date', 'owner_membership_id', 'result', 'row_version', 'signoff_id', 'status', 'updated_at', 'updated_by', 'updated_by_kind', 'waiver_approval_request_id']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['FAILED>IN_PROGRESS', 'FAILED>PASSED', 'FAILED>WAIVED', 'IN_PROGRESS>FAILED', 'IN_PROGRESS>NOT_APPLICABLE', 'IN_PROGRESS>PASSED', 'IN_PROGRESS>WAIVED', 'NOT_STARTED>FAILED', 'NOT_STARTED>IN_PROGRESS', 'NOT_STARTED>NOT_APPLICABLE', 'NOT_STARTED>PASSED', 'NOT_STARTED>WAIVED', 'PASSED>FAILED', 'PASSED>NOT_STARTED', 'WAIVED>FAILED', 'WAIVED>NOT_STARTED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

PREVIOUS: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['comment', 'control_execution_id', 'due_date', 'owner_membership_id', 'result', 'row_version', 'signoff_id', 'status', 'updated_at', 'updated_by', 'updated_by_kind', 'waiver_approval_request_id']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['FAILED>IN_PROGRESS', 'FAILED>PASSED', 'FAILED>WAIVED', 'IN_PROGRESS>FAILED', 'IN_PROGRESS>NOT_APPLICABLE', 'IN_PROGRESS>PASSED', 'IN_PROGRESS>WAIVED', 'NOT_STARTED>FAILED', 'NOT_STARTED>IN_PROGRESS', 'NOT_STARTED>NOT_APPLICABLE', 'NOT_STARTED>PASSED', 'NOT_STARTED>WAIVED', 'PASSED>FAILED', 'WAIVED>FAILED', 'WAIVED>NOT_STARTED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def _replace_function(body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger (NC-18 attributes) — the
    0069 helper, verbatim in shape (SECURITY INVOKER, search_path pinned, $fn$ quoting)."""
    if "$fn$" in body:
        raise ValueError("a trigger function body must not contain $fn$")
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.tg_close_checklist_item__transition() RETURNS trigger "
        f"LANGUAGE plpgsql SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def upgrade() -> None:
    """Allow PASSED tasks to return to NOT_STARTED on reopen."""
    _replace_function(BODY)
    ops.execute("DROP INDEX erev.ux_signoff__signer")
    ops.execute("""
        CREATE UNIQUE INDEX ux_signoff__signer ON erev.signoff
        (tenant_id, subject_type, subject_id, role, signer_id,
         (CASE WHEN subject_type = 'close_checklist_item'
               THEN subject_content_sha256::text ELSE '' END))
    """)


def downgrade() -> None:
    """Restore the prior transition function."""
    ops.execute("LOCK TABLE erev.signoff IN ACCESS EXCLUSIVE MODE")
    ops.execute("ALTER TABLE erev.signoff NO FORCE ROW LEVEL SECURITY")
    ops.execute("""
        DO $check$ BEGIN
          IF EXISTS (SELECT 1 FROM erev.signoff
            GROUP BY tenant_id, subject_type, subject_id, role, signer_id HAVING count(*) > 1)
          THEN RAISE EXCEPTION 'Cannot downgrade 0135: repeated task signoffs must be retained';
          END IF;
        END $check$
    """)
    ops.execute("DROP INDEX erev.ux_signoff__signer")
    ops.execute("""
        CREATE UNIQUE INDEX ux_signoff__signer ON erev.signoff
        (tenant_id, subject_type, subject_id, role, signer_id)
    """)
    ops.execute("ALTER TABLE erev.signoff FORCE ROW LEVEL SECURITY")
    _replace_function(PREVIOUS)
