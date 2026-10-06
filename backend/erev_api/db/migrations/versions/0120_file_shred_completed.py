"""Item FILE-SHRED-DURABLE-ORDER-1 (BUILD_SPEC SOP-5; the supervisor's ruling of 2026-10-01 on
finding B4 of the independent review of the ``EVIDENCE_SHRED`` merge 58eba434; 04 rev 1.237
T-PLT-29; 05 rev 1.171 PRV-07 b, OPR-10): the row of a stored file states when its shred was
completed.

A shred is decided before it is done: the transaction of ``file.shred`` — or of the approved
``EVIDENCE_SHRED`` request — marks the row (``shredded_at`` and its three companions) and writes
the event of the decision, and nothing of the store is touched before that commit. The wrapped
key is destroyed afterwards, and the completion is recorded by whatever finishes it: the
command's own continuation, the same command sent again, or the sweep SCH-16. Until then the
marked row is the durable intent, and it must be findable without asking the store about every
shredded file.

- T-PLT-29 ``file_object.shred_completed_at`` (timestamptz, NULL): set once, when the store's
  part is recorded. ``ck_file_object__shred_completed``: only a row that is marked carries it.
  ``erev_app`` gains the column UPDATE grant, and the DB-03 function
  ``tg_file_object__transition()`` is REPLACED (``CREATE OR REPLACE``: grants and trigger kept —
  the 0065 / 0095 / 0114 precedent) with the fresh rendering of ``erev_api.db.transitions``,
  which admits the column to the allow-list as a write-once member, so DG-ARC-07 holds.
- ``ix_file_object__shred_incomplete (tenant_id, shredded_at)`` over the rows decided and not
  completed: what the sweep reads. Both key columns bound a scan under the table's policy (04
  NC-20: ``uuid``, ``timestamptz``).

Rows shredded before this revision keep the column NULL. A revision runs on the owner connection
without a tenant context and sees no tenant row (DG-MIG-13), so it fills nothing: the sweep
completes those rows — it finds the marker, deletes nothing and records the marker's own instant.

The downgrade removes exactly that, in reverse order (DG-MIG-04): the 0011 body verbatim, the
index, the grant, the check and the column. No table, type or function is added (the erev
function count is unchanged). Both bodies are literals and the module imports ``migration_ops``
only (DG-MIG-12).

Revision 0120, assigned by the supervisor (04 §18 rule 9). ``down_revision`` was 0104, the head
of the lane branch when the revision was written, and is 0117, the head at the supervisor's
merge (ruling R-68 (e)).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0120"
down_revision = "0117"
branch_labels = None
depends_on = None

# The application role of 04 §1.5, spelt as a literal (DG-MIG-12).
APP_ROLE: Final = "erev_app"
TABLE: Final = "file_object"
COLUMN: Final = "shred_completed_at"
CHECK: Final = "ck_file_object__shred_completed"
INDEX: Final = "ix_file_object__shred_incomplete"
INDEX_COLUMNS: Final = ("tenant_id", "shredded_at")
INCOMPLETE: Final = "shredded_at IS NOT NULL AND shred_completed_at IS NULL"

# DB-03: erev_api.db.transitions.transition_trigger_sql("file_object") at this revision.
BODY: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['legal_hold', 'retention_until', 'shred_completed_at', 'shred_reason', 'shredded_at', 'shredded_by', 'shredded_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.shred_completed_at IS NOT NULL AND NEW.shred_completed_at IS DISTINCT FROM OLD.shred_completed_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: shred_completed_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.shred_reason IS NOT NULL AND NEW.shred_reason IS DISTINCT FROM OLD.shred_reason THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: shred_reason of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.shredded_at IS NOT NULL AND NEW.shredded_at IS DISTINCT FROM OLD.shredded_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: shredded_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.shredded_by IS NOT NULL AND NEW.shredded_by IS DISTINCT FROM OLD.shredded_by THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: shredded_by of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.shredded_by_kind IS NOT NULL AND NEW.shredded_by_kind IS DISTINCT FROM OLD.shredded_by_kind THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: shredded_by_kind of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

# The 0011 body (without shred_completed_at), restored by ``downgrade``.
PREVIOUS: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['legal_hold', 'retention_until', 'shred_reason', 'shredded_at', 'shredded_by', 'shredded_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.shred_reason IS NOT NULL AND NEW.shred_reason IS DISTINCT FROM OLD.shred_reason THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: shred_reason of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.shredded_at IS NOT NULL AND NEW.shredded_at IS DISTINCT FROM OLD.shredded_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: shredded_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.shredded_by IS NOT NULL AND NEW.shredded_by IS DISTINCT FROM OLD.shredded_by THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: shredded_by of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.shredded_by_kind IS NOT NULL AND NEW.shredded_by_kind IS DISTINCT FROM OLD.shredded_by_kind THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: shredded_by_kind of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def _replace_function(body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger (NC-18 attributes)."""
    if "$fn$" in body:
        raise ValueError("a trigger function body must not contain $fn$")
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.tg_{TABLE}__transition() RETURNS trigger "
        f"LANGUAGE plpgsql SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def upgrade() -> None:
    ops.execute(f"ALTER TABLE erev.{TABLE} ADD COLUMN {COLUMN} timestamptz NULL")
    ops.execute(
        f"ALTER TABLE erev.{TABLE} ADD CONSTRAINT {CHECK} "
        f"CHECK ({COLUMN} IS NULL OR shredded_at IS NOT NULL)"
    )
    ops.execute(f"GRANT UPDATE ({COLUMN}) ON TABLE erev.{TABLE} TO {APP_ROLE}")
    ops.create_indexes(TABLE, [(INDEX, list(INDEX_COLUMNS), INCOMPLETE)], unique=False)
    _replace_function(BODY)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    _replace_function(PREVIOUS)
    ops.execute(f"DROP INDEX erev.{INDEX}")
    ops.execute(f"REVOKE UPDATE ({COLUMN}) ON TABLE erev.{TABLE} FROM {APP_ROLE}")
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP CONSTRAINT {CHECK}")
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP COLUMN {COLUMN}")
