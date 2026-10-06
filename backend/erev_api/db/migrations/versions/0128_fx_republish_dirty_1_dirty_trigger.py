"""Item FX-REPUBLISH-DIRTY-1 (supervisor ruling R-116 (b) and the rulings of 2026-10-02 on the
lane's pre-build line; 04 rev 1.297; number assigned by the supervisor, register index 277): the
trigger a dirty mark carries, on T-CON-03 ``combination_group`` — one nullable column.

- ``dirty_trigger`` (E-87 ``erev.computation_trigger``): the non-event trigger of the mark that
  ``dirty_since`` stamps, set with it by the approval of an FX rate set version for the groups a
  changed rate can move (``erev_api.domain.close.rate_reach``; 05 RCP-17). A computation that
  consumes the mark without first-including an event is stored under it
  (``contracts.bundles``), so that a difference posted behind a lock has its attribution
  (ENGINE_SPEC_B S15-R-18b: a ``TRIGGER`` row). It is cleared with ``dirty_since``.
- ``ck_combination_group__dirty_trigger``: the column is NULL, or the group is dirty and the
  trigger is ``FX_REPUBLISH`` — the one non-event trigger a mark carries today; a mark of another
  kind widens the check by a revision of its own.

The column joins the IM-S updatable columns of the table (04 T-CON-03 Class line): ``erev_app``
gains ``UPDATE`` on it, and the DB-03 function ``tg_combination_group__transition()`` (installed
by 0038, replaced by 0111 and last by 0126) is replaced with the fresh rendering of
``erev_api.db.transitions`` that names it among the columns the application may move (``CREATE OR
REPLACE FUNCTION``; grants and trigger kept — the 0059 / 0111 / 0126 / 0127 precedent), so
DG-ARC-07 (installed source == fresh rendering) holds. The pair (PROPOSED, VOIDED) of 0126
(item COMBINATION-PROPOSAL-DISCARD-1) stands in both bodies.

No table, type or function is added (the erev function count is unchanged); no row is written
(DG-MIG-07): a group that is dirty when the revision is applied keeps its stamp and carries no
trigger, and is computed under the trigger its caller names, as before. A revision imports nothing
of ``erev_api`` beyond the DDL helpers (DG-MIG-12): both bodies are written out.

The downgrade restores the 0126 function body verbatim, revokes the column grant and drops the
check and the column; it refuses no row (DG-MIG-04): the application of the earlier revision
reads no trigger from a mark. ``down_revision`` was 0122, the integration branch's head when
lane ENG-FX wrote the revision, and is 0124, that branch's head when lane SECFIX-PLT ported the
item onto its tip 68863f956 (supervisor ruling R-68 (e): the chain follows merge order).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0128"
down_revision = "0124"
branch_labels = None
depends_on = None

TABLE: Final = "combination_group"
COLUMN: Final = "dirty_trigger"
COLUMN_TYPE: Final = "erev.computation_trigger"
COLUMN_CHECK: Final = "ck_combination_group__dirty_trigger"
APP_ROLE: Final = "erev_app"

# DB-03: erev_api.db.transitions.transition_trigger_sql("combination_group") after 04 rev 1.297.
BODY: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'criterion', 'dirty_since', 'dirty_trigger', 'head_computation_id', 'inception_date', 'judgement_record_id', 'period_ends_open', 'rationale', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
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

# The body revision 0126 installed (the rendering before 04 rev 1.297), restored by the downgrade.
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
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>APPLIED', 'PROPOSED>SUBMITTED', 'PROPOSED>VOIDED', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED']::text[]) THEN
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
    """The column with its check and grant, and the function that lets the application move it
    (04 T-CON-03 rev 1.297)."""
    ops.execute(f"ALTER TABLE erev.{TABLE} ADD COLUMN {COLUMN} {COLUMN_TYPE} NULL")
    ops.execute(
        f"ALTER TABLE erev.{TABLE} ADD CONSTRAINT {COLUMN_CHECK} "
        f"CHECK ({COLUMN} IS NULL OR (dirty_since IS NOT NULL AND {COLUMN} = 'FX_REPUBLISH'))"
    )
    ops.execute(f"GRANT UPDATE ({COLUMN}) ON TABLE erev.{TABLE} TO {APP_ROLE}")
    _replace_function(BODY)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    _replace_function(PREVIOUS)
    ops.execute(f"REVOKE UPDATE ({COLUMN}) ON TABLE erev.{TABLE} FROM {APP_ROLE}")
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP CONSTRAINT {COLUMN_CHECK}")
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP COLUMN {COLUMN}")
