"""Lane F-RPS-REG, Alembic revision 0126 of register index 266 (item
COMBINATION-PROPOSAL-DISCARD-1; the supervisor's rulings of 2026-10-02 on the lane's reading of
index 253 and on its line; 04 rev 1.289 E-95, T-CON-03; PRD rev 1.196 SM-10, ACT-04): a
PROPOSED combination group is discarded.

- E-95 ``combination_status`` gains ``VOIDED``. No check compares the status of T-CON-03 with
  the type's constants, so nothing else is re-created for the label.
- The DB-03 function ``tg_combination_group__transition()`` gains the pair (PROPOSED, VOIDED).
  Its body is REPLACED (``CREATE OR REPLACE``: grants and trigger kept — the 0065 / 0069 / 0093
  / 0114 / 0118 precedent) with the fresh rendering of ``erev_api.db.transitions``, so
  DG-ARC-07 holds. A discarded group takes no further command: no pair leaves ``VOIDED``.

A proposal that was not submitted had one exit, its submission: a proposal made by mistake was
submitted and withdrawn, and one that named a contract since voided, or since combined
elsewhere, could be neither submitted nor given up.

The downgrade restores the 0111 body verbatim and removes the label through
``remove_enum_value``, which fails while a row still carries ``VOIDED`` (DG-MIG-06): such a row
has no other status to go to. No table, column, index or function is added (the erev function
count is unchanged). Both bodies are literals and the module imports ``migration_ops`` only
(DG-MIG-12).

Revision 0126, assigned by the supervisor (04 §18 rule 9). ``down_revision`` was 0121, the head
of main this head was written on (main d6e7d0f8), and is 0125, the integration branch's head
at the supervisor's merge (ruling R-68 (e)).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0126"
down_revision = "0125"
branch_labels = None
depends_on = None

ENUM: Final = "combination_status"
VALUE: Final = "VOIDED"
GROUP: Final = "combination_group"

# DB-03: erev_api.db.transitions.transition_trigger_sql("combination_group") at this revision.
BODY: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'criterion', 'dirty_since', 'head_computation_id', 'inception_date', 'judgement_record_id', 'period_ends_open', 'rationale', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>APPLIED', 'PROPOSED>SUBMITTED', 'PROPOSED>VOIDED', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

# The 0111 body (without PROPOSED>VOIDED), restored by ``downgrade``.
PREVIOUS: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'criterion', 'dirty_since', 'head_computation_id', 'inception_date', 'judgement_record_id', 'period_ends_open', 'rationale', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>APPLIED', 'PROPOSED>SUBMITTED', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def _replace_function(body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger (NC-18 attributes)."""
    if "$fn$" in body:
        raise ValueError("a trigger function body must not contain $fn$")
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.tg_{GROUP}__transition() RETURNS trigger "
        f"LANGUAGE plpgsql SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def upgrade() -> None:
    ops.add_enum_value(ENUM, VALUE)
    _replace_function(BODY)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    _replace_function(PREVIOUS)
    ops.remove_enum_value(ENUM, VALUE)
