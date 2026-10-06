"""Lane SECFIX-IMP, security finding SC-2 (supervisor rulings R-28, R-29, R-41 (5); 04 rev 1.107
T-IMP-02; 05 rev 1.46 IPL-05): ``import_upload.named_entity_ids`` — the legal entities an upload's
rows name, resolved and written ONCE by the validation job. NULL = not resolved (the upload spans
every entity); ``'{}'`` = a tenant-level upload. The import reads and the ``IMPORT_COMMIT`` request
are scoped by it.

The column joins the IM-S column list: ``erev_app`` gains the column UPDATE grant and the DB-03
function ``tg_import_upload__transition()`` is REPLACED (``CREATE OR REPLACE``: grants and trigger
kept — the 0065 / 0067 precedent) with the body that lists the column among the updatable ones
and as set-once, so DG-ARC-07 (installed source == fresh rendering of
``erev_api.db.transitions``) holds. The downgrade restores the 0044 body verbatim, revokes the
grant and drops the column; no row is rewritten. No table, type or function is added (the erev
function count is unchanged). Every body is a literal (DG-MIG-12).

Revision number 0087 assigned by the supervisor in the SECFIX-IMP package. It was built on
``0072``, the head of the lane branch, which could not take main; the supervisor re-pointed
``down_revision`` to main's head ``0084`` at the merge (ruling R-68 (e); the 0067 / 0072
precedent — never two heads on main).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0087"
down_revision = "0084"
branch_labels = None
depends_on = None

TABLE: Final = "import_upload"
COLUMN: Final = "named_entity_ids"
APP_ROLE: Final = "erev_app"
SIGNATURE: Final = "tg_import_upload__transition()"

# DB-03: erev_api.db.transitions.transition_trigger_sql("import_upload") at this revision.
TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'committed_at', 'control_totals', 'diff_file_id', 'diff_summary', 'error_count', 'job_id', 'named_entity_ids', 'row_count', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind', 'valid_row_count', 'warning_count']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.committed_at IS NOT NULL AND NEW.committed_at IS DISTINCT FROM OLD.committed_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: committed_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.named_entity_ids IS NOT NULL AND NEW.named_entity_ids IS DISTINCT FROM OLD.named_entity_ids THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: named_entity_ids of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>COMMITTING', 'COMMITTING>COMMITTED', 'COMMITTING>FAILED', 'DIFFING>CANCELLED', 'DIFFING>DIFF_READY', 'DIFF_READY>CANCELLED', 'DIFF_READY>SUBMITTED', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED', 'UPLOADED>CANCELLED', 'UPLOADED>VALIDATING', 'VALIDATED>CANCELLED', 'VALIDATED>DIFFING', 'VALIDATING>CANCELLED', 'VALIDATING>INVALID', 'VALIDATING>VALIDATED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501
# The 0044 body (without ``named_entity_ids``), restored by ``downgrade``.
TRANSITION_BODY_0044 = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'committed_at', 'control_totals', 'diff_file_id', 'diff_summary', 'error_count', 'job_id', 'row_count', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind', 'valid_row_count', 'warning_count']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.committed_at IS NOT NULL AND NEW.committed_at IS DISTINCT FROM OLD.committed_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: committed_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>COMMITTING', 'COMMITTING>COMMITTED', 'COMMITTING>FAILED', 'DIFFING>CANCELLED', 'DIFFING>DIFF_READY', 'DIFF_READY>CANCELLED', 'DIFF_READY>SUBMITTED', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED', 'UPLOADED>CANCELLED', 'UPLOADED>VALIDATING', 'VALIDATED>CANCELLED', 'VALIDATED>DIFFING', 'VALIDATING>CANCELLED', 'VALIDATING>INVALID', 'VALIDATING>VALIDATED']::text[]) THEN
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
    ops.execute(f"ALTER TABLE erev.{TABLE} ADD COLUMN {COLUMN} uuid[] NULL")
    ops.execute(f"GRANT UPDATE ({COLUMN}) ON TABLE erev.{TABLE} TO {APP_ROLE}")
    _replace_function(TRANSITION_BODY)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    _replace_function(TRANSITION_BODY_0044)
    ops.execute(f"REVOKE UPDATE ({COLUMN}) ON TABLE erev.{TABLE} FROM {APP_ROLE}")
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP COLUMN {COLUMN}")
