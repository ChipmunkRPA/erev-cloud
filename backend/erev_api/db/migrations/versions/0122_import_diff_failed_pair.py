"""Lane API-GAPS, ACCT backlog row 4 (supervisor rulings R-108 (2) and R-105 (2) of 2026-09-30
and the supervisor's ruling of 2026-10-02 on the failure hook of ``IMPORT_DIFF``; 04 rev 1.270
T-IMP-02; PRD rev 1.186 SM-05; 05 rev 1.185 §5.6): the pair ``DIFFING`` → ``INVALID`` of
``import_upload``.

A dry run whose job ended FAILED — its last attempt met an error, or its worker died — left the
upload ``DIFFING`` for good with nobody told: no pair left the state on a failure. The failure
hook of ``IMPORT_DIFF`` (``erev_api.domain.imports.diff.diff_job_failed``) ends such an upload
``INVALID`` with ``IMPORT_PROCESSING_FAILED``, as the validation's hook does.

The DB-03 function ``tg_import_upload__transition()`` is REPLACED (``CREATE OR REPLACE``: grants
and trigger kept — the 0087 precedent) with the body that lists the pair, so DG-ARC-07 (installed
source == fresh rendering of ``erev_api.db.transitions``) holds. The downgrade restores the 0087
body verbatim. No table, column, type, grant or function is added (the erev function count is
unchanged); no row is rewritten. Every body is a literal (DG-MIG-12).

Revision number 0122 assigned by the supervisor (register index 203). ``down_revision`` is the
head of the lane's tree; the supervisor re-points it to main's head at the merge when main has
moved (ruling R-68 (e) — never two heads on main).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0122"
down_revision = "0127"
branch_labels = None
depends_on = None

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
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>COMMITTING', 'COMMITTING>COMMITTED', 'COMMITTING>FAILED', 'DIFFING>CANCELLED', 'DIFFING>DIFF_READY', 'DIFFING>INVALID', 'DIFF_READY>CANCELLED', 'DIFF_READY>SUBMITTED', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED', 'UPLOADED>CANCELLED', 'UPLOADED>VALIDATING', 'VALIDATED>CANCELLED', 'VALIDATED>DIFFING', 'VALIDATING>CANCELLED', 'VALIDATING>INVALID', 'VALIDATING>VALIDATED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501
# The 0087 body (without the pair ``DIFFING>INVALID``), restored by ``downgrade``.
TRANSITION_BODY_0087 = """
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


def _replace_function(body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger (NC-18 attributes)."""
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.{SIGNATURE} RETURNS trigger LANGUAGE plpgsql "
        f"SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def upgrade() -> None:
    _replace_function(TRANSITION_BODY)


def downgrade() -> None:
    """Restore exactly what upgrade() replaced (DG-MIG-04)."""
    _replace_function(TRANSITION_BODY_0087)
