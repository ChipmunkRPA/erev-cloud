"""Lane SECFIX-ACT, Alembic revision 0118 of register index 174 (the supervisor's rulings of
2026-10-01 on the lane's pre-build line, question J1 (a); items MOD-LINKED-JUDGEMENTS-1 and the
discard of a judgement record; 04 rev 1.242 T-CON-19, E-57; PRD rev 1.169 SM-10): a DRAFT
judgement record is discarded.

- E-57 ``judgement_status`` gains ``VOIDED``. No check compares the status of T-CON-19 with the
  type's constants, so nothing else is re-created for the label.
- The DB-03 function ``tg_judgement_record__transition()`` gains the pair (DRAFT, VOIDED). Its
  body is REPLACED (``CREATE OR REPLACE``: grants and trigger kept — the 0065 / 0069 / 0093 /
  0114 precedent) with the fresh rendering of ``erev_api.db.transitions``, so DG-ARC-07 holds.
  A discarded record takes no further command: no pair leaves ``VOIDED``.

A record a preparer made by mistake had one exit, a reviewer's rejection; and a modification is
not submitted while a record whose subject it is stands DRAFT or SUBMITTED (PRD ERR-95), so a
mistaken draft held its modification until somebody rejected it.

The downgrade restores the 0069 body verbatim and removes the label through
``remove_enum_value``, which fails while a row still carries ``VOIDED`` (DG-MIG-06): such a row
has no other status to go to. No table, column, index or function is added (the erev function
count is unchanged). Both bodies are literals and the module imports ``migration_ops`` only
(DG-MIG-12).

Revision 0118, assigned by the supervisor (04 §18 rule 9). ``down_revision`` was 0117, the
revision of the lane's estimate head, which this head was written on, and is 0120, the head at
the supervisor's merge (ruling R-68 (e)).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0118"
down_revision = "0120"
branch_labels = None
depends_on = None

ENUM: Final = "judgement_status"
VALUE: Final = "VOIDED"
RECORD: Final = "judgement_record"

# DB-03: erev_api.db.transitions.transition_trigger_sql("judgement_record") at this revision.
BODY: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['DRAFT>SUBMITTED', 'DRAFT>VOIDED', 'REJECTED>DRAFT', 'REVIEWED>SUPERSEDED', 'SUBMITTED>REJECTED', 'SUBMITTED>REVIEWED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  IF OLD.status::text = ANY (ARRAY['DRAFT']::text[]) THEN
    RETURN NEW;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'reviewed_at', 'reviewer_id', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.reviewed_at IS NOT NULL AND NEW.reviewed_at IS DISTINCT FROM OLD.reviewed_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: reviewed_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.reviewer_id IS NOT NULL AND NEW.reviewer_id IS DISTINCT FROM OLD.reviewer_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: reviewer_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

# The 0069 body (without DRAFT>VOIDED), restored by ``downgrade``.
PREVIOUS: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['DRAFT>SUBMITTED', 'REJECTED>DRAFT', 'REVIEWED>SUPERSEDED', 'SUBMITTED>REJECTED', 'SUBMITTED>REVIEWED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  IF OLD.status::text = ANY (ARRAY['DRAFT']::text[]) THEN
    RETURN NEW;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'reviewed_at', 'reviewer_id', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.reviewed_at IS NOT NULL AND NEW.reviewed_at IS DISTINCT FROM OLD.reviewed_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: reviewed_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.reviewer_id IS NOT NULL AND NEW.reviewer_id IS DISTINCT FROM OLD.reviewer_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: reviewer_id of %I.%I is already set',
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
        f"CREATE OR REPLACE FUNCTION erev.tg_{RECORD}__transition() RETURNS trigger "
        f"LANGUAGE plpgsql SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def upgrade() -> None:
    ops.add_enum_value(ENUM, VALUE)
    _replace_function(BODY)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    _replace_function(PREVIOUS)
    ops.remove_enum_value(ENUM, VALUE)
