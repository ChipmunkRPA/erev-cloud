"""Item CLO-RATE-AFTER-RUN-1 (the supervisor's ruling of 2026-10-02 08:56 on the lane's pre-build
line; 04 rev 1.291; number assigned by the supervisor, register index 272): what a close run READ
beside its contracts, on T-CLS-01 ``close_run`` — two nullable text columns.

- ``rates_read``: a SHA-256 digest of every exchange rate in force for the tenant, dated on or
  before the period's last day, as the run's first period-end step read them at its record-time
  cutoff — by set, rate type, pair, date and VALUE, not by version: a version that extends a
  set's coverage and repeats the earlier rates leaves the digest as it was.
- ``registry_read``: a SHA-256 digest of the values of the period-pinned parameters (pin ``P`` of
  the parameter registry, the ones a bundle resolves at its cutoff and applies to every period)
  as every entity of the tenant and the run's book resolve them at that cutoff.

The gate ``CLOSE_RUN_COMPLETED`` reads a succeeded run as out of date while either digest differs
from the same read now (``erev_api.domain.close.run_inputs``; ``close.gates``). A time cannot
decide it: a version's ``published_at`` is the START of its approval's unit of work, so an
approval that began before the step and committed after it is "published before" by every clock
stored, and the step did not read it. A run started before this revision holds NULL in both and
is read as before.

The two columns are WRITTEN ONCE, by the step, while the run is ``RUNNING``: they join the IM-S
updatable columns of the table (04 T-CLS-01 Class line), ``erev_app`` gains ``UPDATE`` on them,
and the DB-03 function ``tg_close_run__transition()`` (installed by 0047) is replaced with the
fresh rendering of ``erev_api.db.transitions`` that names them among the columns the application
may move and refuses a second write of either (``CREATE OR REPLACE FUNCTION``; grants and trigger
kept — the 0059 / 0111 precedent), so DG-ARC-07 (installed source == fresh rendering) holds. A
``SUCCEEDED`` run stays frozen but for the ``LOCK`` element of ``steps``: neither column changes
after the run has ended.

No table, type, constraint or function is added (the erev function count is unchanged); no row is
written (DG-MIG-07). A revision imports nothing of ``erev_api`` beyond the DDL helpers (DG-MIG-12):
both bodies are written out.

The downgrade restores the 0047 function body verbatim, revokes the two column grants and drops
the columns; it refuses no row (DG-MIG-04): the application of the earlier revision reads neither
column, and a run closed under this revision is then read as every earlier run is — by its status
and the marks of its contract groups. ``down_revision`` is revision 0121 of the same lane, which
this revision was built on (supervisor ruling R-68 (e): the chain follows merge order).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0127"
down_revision = "0121"
branch_labels = None
depends_on = None

TABLE: Final = "close_run"
# (column, type) in the order they are added; dropped in reverse.
COLUMNS: Final = (("rates_read", "text"), ("registry_read", "text"))
APP_ROLE: Final = "erev_app"

# DB-03: erev_api.db.transitions.transition_trigger_sql("close_run") after 04 rev 1.291.
BODY: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF OLD.status::text = ANY (ARRAY['SUCCEEDED']::text[]) THEN
    SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
      FROM jsonb_each(new_row) n
     WHERE n.key <> ALL (ARRAY['row_version', 'status', 'steps', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
       AND n.value IS DISTINCT FROM old_row -> n.key;
    IF changed IS NOT NULL THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change while status is %s',
                         changed, TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status);
    END IF;
    IF jsonb_typeof(NEW.steps) IS DISTINCT FROM 'array' THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-TRN-001: steps of %I.%I must stay an array',
                         TG_TABLE_SCHEMA, TG_TABLE_NAME);
    END IF;
    IF jsonb_array_length(NEW.steps) <> jsonb_array_length(OLD.steps)
       OR EXISTS (
         SELECT 1
           FROM jsonb_array_elements(OLD.steps) WITH ORDINALITY o(item, ordinal)
           JOIN jsonb_array_elements(NEW.steps) WITH ORDINALITY n(item, ordinal)
             USING (ordinal)
          WHERE o.item IS DISTINCT FROM n.item
            AND NOT (o.item ->> 'step_code' = 'LOCK' AND n.item ->> 'step_code' = 'LOCK')) THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-TRN-001: steps of %I.%I change only in element LOCK while status is %s',
                         TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status);
    END IF;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['counts', 'current_step_code', 'finished_at', 'rates_read', 'registry_read', 'row_version', 'started_at', 'status', 'steps', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.rates_read IS NOT NULL AND NEW.rates_read IS DISTINCT FROM OLD.rates_read THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: rates_read of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.registry_read IS NOT NULL AND NEW.registry_read IS DISTINCT FROM OLD.registry_read THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: registry_read of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.started_at IS NOT NULL AND NEW.started_at IS DISTINCT FROM OLD.started_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: started_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['BLOCKED>RUNNING', 'FAILED>RUNNING', 'PENDING>RUNNING', 'RUNNING>BLOCKED', 'RUNNING>CANCELLED', 'RUNNING>FAILED', 'RUNNING>SUCCEEDED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

# The body revision 0047 installed (the rendering before 04 rev 1.291), restored by the downgrade.
PREVIOUS: Final = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF OLD.status::text = ANY (ARRAY['SUCCEEDED']::text[]) THEN
    SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
      FROM jsonb_each(new_row) n
     WHERE n.key <> ALL (ARRAY['row_version', 'status', 'steps', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
       AND n.value IS DISTINCT FROM old_row -> n.key;
    IF changed IS NOT NULL THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change while status is %s',
                         changed, TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status);
    END IF;
    IF jsonb_typeof(NEW.steps) IS DISTINCT FROM 'array' THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-TRN-001: steps of %I.%I must stay an array',
                         TG_TABLE_SCHEMA, TG_TABLE_NAME);
    END IF;
    IF jsonb_array_length(NEW.steps) <> jsonb_array_length(OLD.steps)
       OR EXISTS (
         SELECT 1
           FROM jsonb_array_elements(OLD.steps) WITH ORDINALITY o(item, ordinal)
           JOIN jsonb_array_elements(NEW.steps) WITH ORDINALITY n(item, ordinal)
             USING (ordinal)
          WHERE o.item IS DISTINCT FROM n.item
            AND NOT (o.item ->> 'step_code' = 'LOCK' AND n.item ->> 'step_code' = 'LOCK')) THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-TRN-001: steps of %I.%I change only in element LOCK while status is %s',
                         TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status);
    END IF;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['counts', 'current_step_code', 'finished_at', 'row_version', 'started_at', 'status', 'steps', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.started_at IS NOT NULL AND NEW.started_at IS DISTINCT FROM OLD.started_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: started_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['BLOCKED>RUNNING', 'FAILED>RUNNING', 'PENDING>RUNNING', 'RUNNING>BLOCKED', 'RUNNING>CANCELLED', 'RUNNING>FAILED', 'RUNNING>SUCCEEDED']::text[]) THEN
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
    """The two columns with their grants, and the function that lets the application write each
    of them once (04 T-CLS-01 rev 1.291)."""
    for name, kind in COLUMNS:
        ops.execute(f"ALTER TABLE erev.{TABLE} ADD COLUMN {name} {kind} NULL")
        ops.execute(f"GRANT UPDATE ({name}) ON TABLE erev.{TABLE} TO {APP_ROLE}")
    _replace_function(BODY)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    _replace_function(PREVIOUS)
    for name, _ in reversed(COLUMNS):
        ops.execute(f"REVOKE UPDATE ({name}) ON TABLE erev.{TABLE} FROM {APP_ROLE}")
        ops.execute(f"ALTER TABLE erev.{TABLE} DROP COLUMN {name}")
