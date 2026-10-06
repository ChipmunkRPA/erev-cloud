"""Item CLO-LOCK-LEGACY-1 (supervisor rulings R-97 (2), R-112 (e) and R-114 (d) of 2026-09-30;
finding F1 of the independent review of revision 0084; number assigned by the supervisor): a line
of the LEGACY book follows the close of the primary book.

04 id amended (rev 1.155): §14.1 DB-07 — ``tg_subledger_line__period_guard`` reads, for a line of
the ``LEGACY`` book, the state row of the tenant's PRIMARY book for the line's entity and period
FIRST, ``FOR SHARE``, and refuses the line (``EREV-LED-003``) when that state is not ``open``,
``closing`` or ``reopened`` — a missing row included. It then reads the line's own state row as
before. ``is_post_reopen`` of a LEGACY line is true when either state is ``reopened``.

The LEGACY book (D-24) takes no journal run and has no close of its own (04 §16.8 rev 1.155), so
its period state rows stayed postable for ever: a LEGACY line was admitted into a period the
primary book had locked, with no primary-book line to hold that lock's state row (the lane's
measurement of 2026-09-30: 7,700.00 into a closed August). With the primary's row shared by the
LEGACY line the lock decision of the primary book — which takes that row ``FOR UPDATE`` and no
second state row — waits for a LEGACY posting in flight and sees its lines, and a posting that
arrives later waits and is refused. A journal line is never of the LEGACY book (T-SL-06), so
``tg_journal_line__period_guard`` keeps the 0084 body.

The function is replaced with ``CREATE OR REPLACE FUNCTION`` — the 0084 precedent: the trigger and
the EXECUTE grants are kept and no function is added (the erev function count is unchanged). The
downgrade restores the 0084 body verbatim (DG-MIG-04). No table, column, constraint, grant or row
changes. A revision imports nothing of ``erev_api`` beyond the DDL helpers and reads no live
constant (DG-MIG-12): both bodies are literals.
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0105"
down_revision = "0107"
branch_labels = None
depends_on = None

SUBLEDGER_GUARD: Final = "tg_subledger_line__period_guard"

# DB-07 (04 rev 1.155): the 0084 body with the primary book's state row read first for a LEGACY
# line.
SUBLEDGER_GUARD_BODY: Final = """
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

# The body revision 0084 installed, restored on downgrade.
SUBLEDGER_GUARD_BODY_0084: Final = """
DECLARE
  period_state_now text;
  origin_end date;
  period_start date;
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id()
     OR NOT coalesce(erev.entity_in_scope(NEW.entity_id), false) THEN
    RETURN NEW;
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
  NEW.is_post_reopen := (period_state_now = 'reopened');
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


def _replace_function(function: str, body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger (NC-18 attributes)."""
    if "$fn$" in body:
        raise ValueError("a trigger function body must not contain $fn$")
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.{function}() RETURNS trigger "
        f"LANGUAGE plpgsql SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def upgrade() -> None:
    """The subledger guard reads the primary book's state row first for a LEGACY line."""
    _replace_function(SUBLEDGER_GUARD, SUBLEDGER_GUARD_BODY)


def downgrade() -> None:
    """Restore the 0084 body verbatim (DG-MIG-04)."""
    _replace_function(SUBLEDGER_GUARD, SUBLEDGER_GUARD_BODY_0084)
