"""Item REOPEN-CLOSING-FLAG-1 (supervisor ruling R-117 (c) of 2026-09-30; PRODUCT DEFECT, a control
point; 04 rev 1.184 T-SL-04, T-REF-06, T-REF-07 and §14.1 DB-07; PRD rev 1.113 BR-CLS-06; number
assigned by the supervisor): a subledger line is a post-reopen line while its period's current lock
record is a ``REOPEN``.

04 ids amended:

- §14.1 DB-07 — ``tg_subledger_line__period_guard`` stored ``is_post_reopen = (state =
  'reopened')``. A reopened period that is soft-closed again reads ``closing``, so the lines posted
  there — the close run's period-end entries, submitted adjustments — were stored ``false``, and
  T-SL-08 ``is_post_close`` of the journal entries made of them with it. The guard now takes
  ``current_lock_id`` from the state row it reads ``FOR SHARE`` and, when it is not null, reads the
  ``kind`` of that ``period_lock`` row: the flag is true when the kind is ``REOPEN`` — the period
  was locked once and is not locked now, whatever its state literal reads. The lock record is read
  in a statement of its own, not joined to the first: a row the guard waited for is re-read under
  the first statement's snapshot, which does not hold a ``REOPEN`` record committed during the
  wait. A period never locked has no record and costs no read. For a line of the ``LEGACY`` book
  (revision 0105: the guard reads the primary book's state row first) the primary's row gives
  its ``current_lock_id`` the same way, and the flag is true when either row is under a
  ``REOPEN`` record — 0105 stored "either state is ``reopened``". ``tg_journal_line__period_guard``
  stores no flag and keeps the 0084 body.
- T-REF-07 ``ck_period_state_transition__reason_code`` — the terms of ``closing → open`` and
  ``closed → reopened`` compared a NULL reason with their subset, which is unknown and passes a
  ``CHECK``, although the column note says "Required". Both terms now refuse NULL, as the term of
  ``closing → reopened`` has done since 0107.

The function is replaced with ``CREATE OR REPLACE FUNCTION`` — the 0084 / 0105 precedent: the
trigger and the EXECUTE grants are kept and no function is added (the erev function count is
unchanged). The downgrade restores the 0105 body and the 0107 check verbatim (DG-MIG-04). The
upgrade needs a table without a ``closing → open`` or ``closed → reopened`` row that has no
reason: ``ADD CONSTRAINT`` refuses such a row by the constraint's name and the upgrade stops
there (DG-MIG-06) — the table is append-only, so no revision can give a row its reason; every
command has required it. No table, column, type, grant or row changes. A revision imports
nothing of ``erev_api`` beyond the DDL helpers and reads no live constant (DG-MIG-12): every
body and check is a literal.

Revision 0113 (assigned by the supervisor) on 0099, main's head at the lane's merge of main
2f97b1ac (supervisor ruling R-68 (e): a revision keeps its number and follows the head it finds;
it was built on 0107 and its body on 0084's, and was rebuilt on the body of 0105 when lane
FIX-D2's LEGACY rule landed first).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0113"
down_revision = "0099"
branch_labels = None
depends_on = None

TABLE: Final = "period_state_transition"
SUBLEDGER_GUARD: Final = "tg_subledger_line__period_guard"
REASON_CHECK: Final = "ck_period_state_transition__reason_code"

_CANCEL_REASONS: Final = "'CLOSE_RESTARTED', 'DATA_CORRECTION_PENDING', 'OTHER'"
_REOPEN_REASONS: Final = "'ERROR_CORRECTION', 'LATE_SOURCE_DATA', 'AUDIT_ADJUSTMENT', 'OTHER'"

# DB-07 (04 rev 1.184): the 0105 body with ``is_post_reopen`` read from the lock record of the
# line's own state row and, for a LEGACY line, of the primary book's.
SUBLEDGER_GUARD_BODY: Final = """
DECLARE
  period_state_now text;
  lock_now uuid;
  lock_kind_now text;
  primary_book erev.book.code%TYPE;
  primary_state_now text;
  primary_lock_now uuid;
  primary_lock_kind_now text;
  origin_end date;
  period_start date;
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id()
     OR NOT coalesce(erev.entity_in_scope(NEW.entity_id), false) THEN
    RETURN NEW;
  END IF;
  IF NEW.book_code = 'LEGACY' THEN
    SELECT b.code INTO primary_book
      FROM erev.book b
     WHERE b.tenant_id = NEW.tenant_id AND b.is_primary;
    SELECT s.state::text, s.current_lock_id INTO primary_state_now, primary_lock_now
      FROM erev.period_state s
     WHERE s.tenant_id = NEW.tenant_id AND s.entity_id = NEW.entity_id
       AND s.book_code = primary_book AND s.period_id = NEW.period_id
       FOR SHARE;
    IF primary_state_now IS NULL OR primary_state_now NOT IN ('open', 'closing', 'reopened') THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-LED-003: period %s of entity %s is %s in book %s, whose close the '
                         'LEGACY book follows, so line %s cannot post into it', NEW.period_id,
                         NEW.entity_id, coalesce(primary_state_now, 'without a state'),
                         coalesce(primary_book::text, 'the primary book'), NEW.id);
    END IF;
  END IF;
  SELECT s.state::text, s.current_lock_id INTO period_state_now, lock_now
    FROM erev.period_state s
   WHERE s.tenant_id = NEW.tenant_id AND s.entity_id = NEW.entity_id
     AND s.book_code = NEW.book_code AND s.period_id = NEW.period_id
     FOR SHARE;
  IF period_state_now IS NULL OR period_state_now NOT IN ('open', 'closing', 'reopened') THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-003: period %s of entity %s is %s in book %s, so line %s cannot '
                       'post into it', NEW.period_id, NEW.entity_id,
                       coalesce(period_state_now, 'without a state'), NEW.book_code, NEW.id);
  END IF;
  IF lock_now IS NOT NULL THEN
    SELECT l.kind::text INTO lock_kind_now
      FROM erev.period_lock l
     WHERE l.tenant_id = NEW.tenant_id AND l.id = lock_now;
  END IF;
  IF primary_lock_now IS NOT NULL THEN
    SELECT l.kind::text INTO primary_lock_kind_now
      FROM erev.period_lock l
     WHERE l.tenant_id = NEW.tenant_id AND l.id = primary_lock_now;
  END IF;
  NEW.is_post_reopen := (coalesce(lock_kind_now = 'REOPEN', false)
                         OR coalesce(primary_lock_kind_now = 'REOPEN', false));
  IF NEW.origin_period_id IS NOT NULL THEN
    SELECT o.end_date INTO origin_end
      FROM erev.period o
     WHERE o.tenant_id = NEW.tenant_id AND o.id = NEW.origin_period_id;
    SELECT p.start_date INTO period_start
      FROM erev.period p
     WHERE p.tenant_id = NEW.tenant_id AND p.id = NEW.period_id;
    IF origin_end IS NULL OR origin_end >= period_start THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-LED-003: origin period %s of line %s does not end before period %s '
                         'starts', NEW.origin_period_id, NEW.id, NEW.period_id);
    END IF;
  END IF;
  RETURN NEW;
END
"""

# The body revision 0105 installed, restored on downgrade.
SUBLEDGER_GUARD_BODY_0105: Final = """
DECLARE
  period_state_now text;
  primary_book erev.book.code%TYPE;
  primary_state_now text;
  origin_end date;
  period_start date;
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id()
     OR NOT coalesce(erev.entity_in_scope(NEW.entity_id), false) THEN
    RETURN NEW;
  END IF;
  IF NEW.book_code = 'LEGACY' THEN
    SELECT b.code INTO primary_book
      FROM erev.book b
     WHERE b.tenant_id = NEW.tenant_id AND b.is_primary;
    SELECT s.state::text INTO primary_state_now
      FROM erev.period_state s
     WHERE s.tenant_id = NEW.tenant_id AND s.entity_id = NEW.entity_id
       AND s.book_code = primary_book AND s.period_id = NEW.period_id
       FOR SHARE;
    IF primary_state_now IS NULL OR primary_state_now NOT IN ('open', 'closing', 'reopened') THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-LED-003: period %s of entity %s is %s in book %s, whose close the '
                         'LEGACY book follows, so line %s cannot post into it', NEW.period_id,
                         NEW.entity_id, coalesce(primary_state_now, 'without a state'),
                         coalesce(primary_book::text, 'the primary book'), NEW.id);
    END IF;
  END IF;
  SELECT s.state::text INTO period_state_now
    FROM erev.period_state s
   WHERE s.tenant_id = NEW.tenant_id AND s.entity_id = NEW.entity_id
     AND s.book_code = NEW.book_code AND s.period_id = NEW.period_id
     FOR SHARE;
  IF period_state_now IS NULL OR period_state_now NOT IN ('open', 'closing', 'reopened') THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-003: period %s of entity %s is %s in book %s, so line %s cannot '
                       'post into it', NEW.period_id, NEW.entity_id,
                       coalesce(period_state_now, 'without a state'), NEW.book_code, NEW.id);
  END IF;
  NEW.is_post_reopen := (period_state_now = 'reopened'
                         OR coalesce(primary_state_now, '') = 'reopened');
  IF NEW.origin_period_id IS NOT NULL THEN
    SELECT o.end_date INTO origin_end
      FROM erev.period o
     WHERE o.tenant_id = NEW.tenant_id AND o.id = NEW.origin_period_id;
    SELECT p.start_date INTO period_start
      FROM erev.period p
     WHERE p.tenant_id = NEW.tenant_id AND p.id = NEW.period_id;
    IF origin_end IS NULL OR origin_end >= period_start THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-LED-003: origin period %s of line %s does not end before period %s '
                         'starts', NEW.origin_period_id, NEW.id, NEW.period_id);
    END IF;
  END IF;
  RETURN NEW;
END
"""

# T-REF-07 ``reason_code`` (04 rev 1.184): each of the three pairs carries a reason of its subset.
# ``NULL IN (…)`` is NULL, which a CHECK lets pass; ``coalesce(…, false)`` refuses it.
REASON_SQL: Final = (
    "(NOT (from_state = 'closing' AND to_state = 'open') "
    f"OR coalesce(reason_code IN ({_CANCEL_REASONS}), false)) "
    "AND (NOT (from_state = 'closing' AND to_state = 'reopened') "
    f"OR coalesce(reason_code IN ({_CANCEL_REASONS}), false)) "
    "AND (NOT (from_state = 'closed' AND to_state = 'reopened') "
    f"OR coalesce(reason_code IN ({_REOPEN_REASONS}), false))"
)

# The check revision 0107 installed, restored on downgrade.
REASON_SQL_0107: Final = (
    "(NOT (from_state = 'closing' AND to_state = 'open') "
    "OR reason_code IN ('CLOSE_RESTARTED', 'DATA_CORRECTION_PENDING', 'OTHER')) "
    "AND (NOT (from_state = 'closing' AND to_state = 'reopened') "
    "OR coalesce(reason_code IN ('CLOSE_RESTARTED', 'DATA_CORRECTION_PENDING', 'OTHER'), false)) "
    "AND (NOT (from_state = 'closed' AND to_state = 'reopened') "
    "OR reason_code IN ('ERROR_CORRECTION', 'LATE_SOURCE_DATA', 'AUDIT_ADJUSTMENT', "
    "'OTHER'))"
)


def _replace_function(function: str, body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger (NC-18 attributes)."""
    if "$fn$" in body:
        raise ValueError("a trigger function body must not contain $fn$")
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.{function}() RETURNS trigger "
        f"LANGUAGE plpgsql SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def _replace_check(name: str, expression: str) -> None:
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP CONSTRAINT {name}")
    ops.execute(f"ALTER TABLE erev.{TABLE} ADD CONSTRAINT {name} CHECK ({expression})")


def upgrade() -> None:
    """The guard first, then the reason check."""
    _replace_function(SUBLEDGER_GUARD, SUBLEDGER_GUARD_BODY)
    _replace_check(REASON_CHECK, REASON_SQL)


def downgrade() -> None:
    """Restore the 0107 check and the 0105 body verbatim, in reverse order (DG-MIG-04)."""
    _replace_check(REASON_CHECK, REASON_SQL_0107)
    _replace_function(SUBLEDGER_GUARD, SUBLEDGER_GUARD_BODY_0105)
