"""BUILD_SPEC CLO-16 / CLO-17 (supervisor ruling R-54 of 2026-09-30; number assigned by the
supervisor): the reconciliation generation job and the columns a reconciliation's later commands
write.

04 ids amended (rev 1.121): E-14 ``job_kind`` gains ``RECONCILIATION_GENERATE`` — ``POST
/reconciliations`` answers 202 with a job (API-R-40; 05 §5.6 queue ``close``) — and T-PLT-27
``job.subject_type`` admits ``reconciliation``, the resource that job works on
(``ck_job__subject_type`` is replaced with the 0012 list plus that literal). T-CLS-06
``reconciliation``: ``source_file_id`` and ``sync_run_id`` join the IM-S updatable columns as
write-once members — set by ``POST /reconciliations/{id}/attach-trial-balance`` while NULL, never
changed afterwards — and the DB-03 pair ``REOPENED`` → ``DRAFT`` is retired: every regeneration
inserts a new ``DRAFT`` row and a ``REOPENED`` row is history (D-98 79, extended by R-54 (b)).
``tg_reconciliation__transition`` is replaced with the body
``erev_api.db.transitions.transition_trigger_sql("reconciliation")`` renders after the rule change
(DG-ARC-07 compares the installed function with a fresh rendering), and ``erev_app`` gains
``UPDATE (source_file_id, sync_run_id)`` on the table. ``CREATE OR REPLACE`` keeps the function's
grants and its trigger; no table, column or function is added (the erev function count is
unchanged). The downgrade restores the 0059 body verbatim, revokes the column grants, restores the
0012 subject-type check and rewrites the type without the label through ``remove_enum_value``
(DG-MIG-06); the last two fail while a job row still carries the subject type or the kind. A
revision imports nothing of ``erev_api`` beyond the DDL helpers (DG-MIG-12): both bodies are
literals.
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

# The application role of 04 §1.5 (``erev_api.db.session.APP_ROLE``), spelt as a literal: DG-MIG-12
# keeps a revision's imports to the DDL helpers, so the name is not read from the live module.
APP_ROLE: Final = "erev_app"

revision = "0095"
down_revision = "0073"
branch_labels = None
depends_on = None

ENUM: Final = "job_kind"
VALUE: Final = "RECONCILIATION_GENERATE"
TABLE: Final = "reconciliation"
FUNCTION: Final = "tg_reconciliation__transition()"
# 04 T-CLS-06 rev 1.121: the write-once columns this revision makes updatable.
SET_ONCE_COLUMNS: Final = ("source_file_id", "sync_run_id")
JOB_TABLE: Final = "job"
SUBJECT_CHECK: Final = "ck_job__subject_type"
# 04 T-PLT-27 ``subject_type``: the list of revision 0012, then the literal of rev 1.121.
PREVIOUS_SUBJECT_TYPES: Final = (
    "contract",
    "combination_group",
    "modification",
    "estimate_version",
    "import_upload",
    "journal_run",
    "close_run",
    "report_run",
    "evidence_pack",
    "ssp_calculator_run",
    "sync_run",
    "migration_batch",
    "registry_version",
    "ai_proposal",
    "tenant",
)
SUBJECT_TYPES: Final = (*PREVIOUS_SUBJECT_TYPES, "reconciliation")

# DB-03: erev_api.db.transitions.transition_trigger_sql("reconciliation") after ruling R-54.
TRANSITION_BODY: Final = """
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

# The 0059 body, restored verbatim on downgrade (DG-MIG-04).
PREVIOUS_TRANSITION_BODY: Final = """
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


def _replace_function(signature: str, body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger; NC-18 attributes."""
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.{signature} RETURNS trigger LANGUAGE plpgsql "
        f"SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def _replace_subject_check(subject_types: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{subject}'" for subject in subject_types)
    ops.execute(f"ALTER TABLE erev.{JOB_TABLE} DROP CONSTRAINT {SUBJECT_CHECK}")
    ops.execute(
        f"ALTER TABLE erev.{JOB_TABLE} ADD CONSTRAINT {SUBJECT_CHECK} "
        f"CHECK (subject_type IS NULL OR subject_type IN ({listed}))"
    )


def upgrade() -> None:
    """Add the job kind and its subject type, grant the write-once columns and install the
    re-rendered DB-03 body."""
    ops.add_enum_value(ENUM, VALUE)
    _replace_subject_check(SUBJECT_TYPES)
    columns = ", ".join(SET_ONCE_COLUMNS)
    ops.execute(f"GRANT UPDATE ({columns}) ON TABLE erev.{TABLE} TO {APP_ROLE}")
    _replace_function(FUNCTION, TRANSITION_BODY)


def downgrade() -> None:
    """Restore the 0059 body, revoke the column grants, restore the 0012 subject types and remove
    the job kind (DG-MIG-04)."""
    _replace_function(FUNCTION, PREVIOUS_TRANSITION_BODY)
    columns = ", ".join(SET_ONCE_COLUMNS)
    ops.execute(f"REVOKE UPDATE ({columns}) ON TABLE erev.{TABLE} FROM {APP_ROLE}")
    _replace_subject_check(PREVIOUS_SUBJECT_TYPES)
    ops.remove_enum_value(ENUM, VALUE)
