"""Item JRN-FAILED-CANCEL-1 (supervisor ruling R-112 (c) of 2026-09-30; 04 rev 1.159 E-34, §16.7
"Journal commands", T-SL-07 "The ways out of ``failed``"; PRD rev 1.88 SM-08): E-34 gains the pair
``failed`` → ``cancelled`` for ``journal_run`` and ``journal_batch``. A batch its ledger can never
accept as generated held the acknowledgement gate of its period for good: a ``failed`` run had no
way out but a retry. The run is now cancelled — after the worker asked the ledger whether it
holds one of the failed batches — and the period is calculated again.

This revision replaces the bodies of ``tg_journal_run__transition`` and
``tg_journal_batch__transition`` (installed by 0046) with the fresh rendering (``CREATE OR REPLACE
FUNCTION``; grants and triggers kept — the 0065 / 0069 / 0093 precedent), so DG-ARC-07 (installed
source == fresh rendering) holds; the downgrade restores the 0046 literals verbatim (DG-MIG-04).
In each body one line changes: the list of admitted pairs gains ``failed>cancelled``. No table,
column, type or function is added (the erev function count is unchanged). A revision imports
nothing of ``erev_api`` beyond the DDL helpers (DG-MIG-12): the four bodies are literals. Revision
0108, assigned by the supervisor (04 §18 rule 9); ``down_revision`` was the head the lane found
at each merge of main (0101 at 855af940, 0099 at 20531d3b; supervisor ruling R-68 (e)) and is
main's head 0112 since the supervisor's merge of the lane.
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0108"
down_revision = "0112"
branch_labels = None
depends_on = None

RUN_BODY: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['acknowledged_at', 'approval_request_id', 'approved_at', 'cancelled_at', 'exported_at', 'row_version', 'state', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.acknowledged_at IS NOT NULL AND NEW.acknowledged_at IS DISTINCT FROM OLD.acknowledged_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: acknowledged_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.approved_at IS NOT NULL AND NEW.approved_at IS DISTINCT FROM OLD.approved_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: approved_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.cancelled_at IS NOT NULL AND NEW.cancelled_at IS DISTINCT FROM OLD.cancelled_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: cancelled_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.state IS DISTINCT FROM OLD.state
     AND (OLD.state::text || '>' || NEW.state::text) <> ALL (ARRAY['approved>cancelled', 'approved>exported', 'draft>approved', 'draft>cancelled', 'exported>acknowledged', 'exported>failed', 'failed>cancelled', 'failed>exported']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: state of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.state, NEW.state);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

RUN_PREVIOUS: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['acknowledged_at', 'approval_request_id', 'approved_at', 'cancelled_at', 'exported_at', 'row_version', 'state', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.acknowledged_at IS NOT NULL AND NEW.acknowledged_at IS DISTINCT FROM OLD.acknowledged_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: acknowledged_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.approved_at IS NOT NULL AND NEW.approved_at IS DISTINCT FROM OLD.approved_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: approved_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.cancelled_at IS NOT NULL AND NEW.cancelled_at IS DISTINCT FROM OLD.cancelled_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: cancelled_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.state IS DISTINCT FROM OLD.state
     AND (OLD.state::text || '>' || NEW.state::text) <> ALL (ARRAY['approved>cancelled', 'approved>exported', 'draft>approved', 'draft>cancelled', 'exported>acknowledged', 'exported>failed', 'failed>exported']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: state of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.state, NEW.state);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

BATCH_BODY: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['acknowledged_at', 'attempt_count', 'export_file_id', 'export_sha256', 'exported_at', 'last_error', 'outbox_message_id', 'row_version', 'state', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.acknowledged_at IS NOT NULL AND NEW.acknowledged_at IS DISTINCT FROM OLD.acknowledged_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: acknowledged_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.state IS DISTINCT FROM OLD.state
     AND (OLD.state::text || '>' || NEW.state::text) <> ALL (ARRAY['approved>cancelled', 'approved>exported', 'draft>approved', 'draft>cancelled', 'exported>acknowledged', 'exported>failed', 'failed>cancelled', 'failed>exported']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: state of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.state, NEW.state);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

BATCH_PREVIOUS: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['acknowledged_at', 'attempt_count', 'export_file_id', 'export_sha256', 'exported_at', 'last_error', 'outbox_message_id', 'row_version', 'state', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.acknowledged_at IS NOT NULL AND NEW.acknowledged_at IS DISTINCT FROM OLD.acknowledged_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: acknowledged_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.state IS DISTINCT FROM OLD.state
     AND (OLD.state::text || '>' || NEW.state::text) <> ALL (ARRAY['approved>cancelled', 'approved>exported', 'draft>approved', 'draft>cancelled', 'exported>acknowledged', 'exported>failed', 'failed>exported']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: state of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.state, NEW.state);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def _replace_function(table: str, body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger (NC-18 attributes) — the
    0069 helper, verbatim in shape (SECURITY INVOKER, search_path pinned, $fn$ quoting)."""
    if "$fn$" in body:
        raise ValueError("a trigger function body must not contain $fn$")
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.tg_{table}__transition() RETURNS trigger "
        f"LANGUAGE plpgsql SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def upgrade() -> None:
    _replace_function("journal_run", RUN_BODY)
    _replace_function("journal_batch", BATCH_BODY)


def downgrade() -> None:
    """Restore exactly the 0046 bodies, verbatim (DG-MIG-04)."""
    _replace_function("journal_batch", BATCH_PREVIOUS)
    _replace_function("journal_run", RUN_PREVIOUS)
