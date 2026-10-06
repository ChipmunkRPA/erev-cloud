"""BUILD_SPEC CLO-12 (supervisor ruling R-51 (b); 04 rev 1.120 T-SL-05 / E-94 note; PRD rev 1.49
SM-10): the ``manual_adjustment`` DB-03 spec gains the pairs of T-CON-06 — (SUBMITTED, DRAFT), the
request withdrawn by its preparer or voided as stale; (REJECTED, DRAFT), revise and resubmit; and
(DRAFT, VOIDED), discard. PRD SM-10 had no way back from SUBMITTED and no way to discard a DRAFT,
so a mistaken draft counted as pending for ever (``MANUAL_ADJUSTMENTS_CLEARED``, REQ-JE-019).

This revision replaces the body of ``tg_manual_adjustment__transition`` (installed by 0046,
re-rendered by 0069) with the fresh rendering (``CREATE OR REPLACE FUNCTION``; grants and trigger
kept — the 0065 / 0069 / 0070 precedent), so DG-ARC-07 (installed source == fresh rendering)
holds; the downgrade restores the 0069 literal verbatim (DG-MIG-04). No table, column, type or
function is added (the erev function count is unchanged). A revision imports nothing of
``erev_api`` beyond the DDL helpers (DG-MIG-12): both bodies are literals. Revision 0093, assigned
by the supervisor (04 §18 rule 9); ``down_revision`` is the head the lane found at its last merge
of main (0092, lane SECFIX-PLT; supervisor ruling R-68 (e)) and is re-pointed when another lane's
revision lands first.
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None

TABLE: Final = "manual_adjustment"

BODY: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>POSTED', 'DRAFT>SUBMITTED', 'DRAFT>VOIDED', 'POSTED>VOIDED', 'REJECTED>DRAFT', 'SUBMITTED>APPROVED', 'SUBMITTED>DRAFT', 'SUBMITTED>REJECTED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  IF OLD.status::text = ANY (ARRAY['DRAFT']::text[]) THEN
    RETURN NEW;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['applied_event_id', 'approval_request_id', 'is_deferred_past_lock', 'row_version', 'status', 'subledger_posting_id', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.applied_event_id IS NOT NULL AND NEW.applied_event_id IS DISTINCT FROM OLD.applied_event_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: applied_event_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.subledger_posting_id IS NOT NULL AND NEW.subledger_posting_id IS DISTINCT FROM OLD.subledger_posting_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: subledger_posting_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
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
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>POSTED', 'DRAFT>SUBMITTED', 'POSTED>VOIDED', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  IF OLD.status::text = ANY (ARRAY['DRAFT']::text[]) THEN
    RETURN NEW;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['applied_event_id', 'approval_request_id', 'is_deferred_past_lock', 'row_version', 'status', 'subledger_posting_id', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.applied_event_id IS NOT NULL AND NEW.applied_event_id IS DISTINCT FROM OLD.applied_event_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: applied_event_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.subledger_posting_id IS NOT NULL AND NEW.subledger_posting_id IS DISTINCT FROM OLD.subledger_posting_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: subledger_posting_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
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
        f"CREATE OR REPLACE FUNCTION erev.tg_{TABLE}__transition() RETURNS trigger "
        f"LANGUAGE plpgsql SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def upgrade() -> None:
    _replace_function(BODY)


def downgrade() -> None:
    """Restore exactly the 0069 body, verbatim (DG-MIG-04)."""
    _replace_function(PREVIOUS)
