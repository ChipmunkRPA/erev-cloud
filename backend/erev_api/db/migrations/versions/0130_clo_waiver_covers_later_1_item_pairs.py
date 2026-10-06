"""Item CLO-WAIVER-COVERS-LATER-1 (the supervisor's ruling of 2026-10-02 17:32 on the lane's line;
04 rev 1.305; number assigned by the supervisor, register index 283): a waiver of a close gate
ends with what it covered — two DB-03 pairs more on T-CLS-03 ``close_checklist_item``.

A ``WAIVED`` item was final: no pair led out of it. Measured before the item: a waiver asked for
a gate at count 1 and approved at 2 stayed ``WAIVED`` while two more arrived, the lock was
requested and approved, and its certification stores the gate ``WAIVED`` with count 4 and
waived count 2; a waiver given before a lock stayed ``WAIVED`` through the period's reopen.

- ``WAIVED`` → ``FAILED``: written by the evaluation that reads a count above the count the
  waiver was approved for (``close.gates``); a waiver can then be asked for what stands.
- ``WAIVED`` → ``NOT_STARTED``: written by the ``PERIOD_REOPEN`` decision for every waived item
  of the period (``close.commands``); the re-lock is a certification of its own.

The DB-03 function ``tg_close_checklist_item__transition()`` (installed by 0047) is replaced with
the fresh rendering of ``erev_api.db.transitions`` (``CREATE OR REPLACE FUNCTION``; grants and
trigger kept — the 0059 / 0111 / 0127 precedent), so DG-ARC-07 (installed source == fresh
rendering) holds. No table, column, type, grant or constraint changes and no row is written
(DG-MIG-07); both bodies are written out (DG-MIG-12).

The downgrade restores the 0047 body verbatim and refuses no row (DG-MIG-04): an item this
revision moved out of ``WAIVED`` holds ``FAILED`` or ``NOT_STARTED``, statuses the earlier
application evaluates as it does any item. ``down_revision`` is 0126, the head of the supervisor's
integration branch at its merge of this head; the revision was written on 0127 of the same lane
and stood on 0125 at the lane's merge of that branch's tip 0a626426 (supervisor ruling R-68 (e):
the chain follows merge order).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0130"
down_revision = "0126"
branch_labels = None
depends_on = None

TABLE: Final = "close_checklist_item"

# DB-03: erev_api.db.transitions.transition_trigger_sql("close_checklist_item") after 04 rev 1.305.
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
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['FAILED>IN_PROGRESS', 'FAILED>PASSED', 'FAILED>WAIVED', 'IN_PROGRESS>FAILED', 'IN_PROGRESS>NOT_APPLICABLE', 'IN_PROGRESS>PASSED', 'IN_PROGRESS>WAIVED', 'NOT_STARTED>FAILED', 'NOT_STARTED>IN_PROGRESS', 'NOT_STARTED>NOT_APPLICABLE', 'NOT_STARTED>PASSED', 'NOT_STARTED>WAIVED', 'PASSED>FAILED', 'WAIVED>FAILED', 'WAIVED>NOT_STARTED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

# The body revision 0047 installed (the rendering before 04 rev 1.305), restored by the downgrade.
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
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['FAILED>IN_PROGRESS', 'FAILED>PASSED', 'FAILED>WAIVED', 'IN_PROGRESS>FAILED', 'IN_PROGRESS>NOT_APPLICABLE', 'IN_PROGRESS>PASSED', 'IN_PROGRESS>WAIVED', 'NOT_STARTED>FAILED', 'NOT_STARTED>IN_PROGRESS', 'NOT_STARTED>NOT_APPLICABLE', 'NOT_STARTED>PASSED', 'NOT_STARTED>WAIVED', 'PASSED>FAILED']::text[]) THEN
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
        f"CREATE OR REPLACE FUNCTION erev.tg_{TABLE}__transition() RETURNS trigger "
        f"LANGUAGE plpgsql SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def upgrade() -> None:
    """The function that admits the two pairs out of ``WAIVED`` (04 T-CLS-03 rev 1.305)."""
    _replace_function(BODY)


def downgrade() -> None:
    """The function as 0047 installed it: ``WAIVED`` is final again (DG-MIG-04)."""
    _replace_function(PREVIOUS)
