"""BUILD_SPEC item CLO-6 (the period lock), security finding SC-1 (lane FIX-D2 slice 3 rework;
supervisor rulings R-31, R-40 (b) and R-40 (c) of 2026-09-30; 04 rev 1.113 §14.1 DB-07 and
T-CLS-04; ENGINE_SPEC_B S15-R-18c).

04 ids amended:

- §14.1 DB-07 — ``tg_subledger_line__period_guard`` (0040) and ``tg_journal_line__period_guard``
  (0046) read the ``period_state`` row of the line's entity, book and period ``FOR SHARE``. The
  landed bodies read it with a plain ``SELECT``, so a posting whose lines were inserted while the
  period was ``closing`` committed after the lock decision had read the ledger, frozen its
  datasets and moved the period to ``closed`` (SC-1: the period closed with lines its lock's
  head and datasets did not hold). A line insert now holds the row until its transaction ends and
  every change of a period's state takes the row ``FOR UPDATE`` (``close.gates.period_scope``,
  ``close.commands._move``) or updates it, so the lock decision waits for the postings in flight
  and sees their lines, and a posting that arrives later waits and then reads ``closed``
  (``EREV-LED-003``). Both functions are replaced with ``CREATE OR REPLACE FUNCTION`` — the 0065 /
  0069 precedent: the triggers and the EXECUTE grants are kept, no function is added (the erev
  function count is unchanged) — NOT corrected in 0040 / 0046, because databases already past
  those revisions must receive the bodies by upgrade. The downgrade restores the two previous
  literals verbatim (DG-MIG-04).
- T-CLS-04 ``period_lock`` gains ``cutoff_known_at`` (timestamptz): the instant a ``LOCK`` row's
  datasets are frozen at (S15-R-18c), present on a ``LOCK`` row and on no other kind —
  ``ck_period_lock__cutoff_known_at``. IM-A: the class's table-level SELECT and INSERT grants and
  its DB-01 triggers cover the column (the 0061 precedent).

Rows written before this revision (DG-MIG-13; D-99 (3)): nothing is backfilled — a revision runs
as ``erev_owner`` without a tenant context, so an UPDATE sees no row under the forced row-level
security and DB-01 refuses it, and ``created_at`` is not the cutoff of a lock decided on a server
clock ahead of the application clock. The check is therefore added ``NOT VALID`` — enforced for
every row written from here on — and validated in the same transaction: on a database without an
earlier ``LOCK`` row (every database created at head) it ends validated; on a pre-release database
that holds earlier locks the validation's ``check_violation`` is caught, a NOTICE names the
revision, the constraint stays ``NOT VALID`` and those rows keep NULL. The validation is the
RLS-independent probe (it scans every physical row); no row is changed, no date synthesized, RLS
and roles are untouched. A plain valid CHECK would refuse the whole revision on such a database,
and the guards above would not reach it.

Revision 0084 (assigned by the supervisor) on 0095, main's head at the merge of main 80284cfe
(re-pointed from 0073; supervisor ruling R-68 (e): a revision keeps its number and follows the
head it finds). A revision imports nothing of ``erev_api`` beyond the DDL helpers and reads no
live constant (DG-MIG-12): every body is a literal.
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0084"
down_revision = "0095"
branch_labels = None
depends_on = None

SUBLEDGER_GUARD: Final = "tg_subledger_line__period_guard"
JOURNAL_GUARD: Final = "tg_journal_line__period_guard"
LOCK_TABLE: Final = "erev.period_lock"
CUTOFF_COLUMN: Final = "cutoff_known_at"
CUTOFF_CHECK: Final = "ck_period_lock__cutoff_known_at"

# DB-07 (04 rev 1.113): the 0040 body with the period's state row read FOR SHARE.
SUBLEDGER_GUARD_BODY: Final = """
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

# The body revision 0040 installed, restored on downgrade.
SUBLEDGER_GUARD_BODY_0040: Final = """
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
     AND s.book_code = NEW.book_code AND s.period_id = NEW.period_id;
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

# DB-07 (04 rev 1.113): the 0046 body with the period's state row read FOR SHARE.
JOURNAL_GUARD_BODY: Final = """
DECLARE
  period_state_now text;
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
      MESSAGE = format('EREV-LED-003: period %s of entity %s is %s in book %s, so journal line %s '
                       'cannot post into it', NEW.period_id, NEW.entity_id,
                       coalesce(period_state_now, 'without a state'), NEW.book_code, NEW.id);
  END IF;
  RETURN NEW;
END
"""

# The body revision 0046 installed, restored on downgrade.
JOURNAL_GUARD_BODY_0046: Final = """
DECLARE
  period_state_now text;
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id()
     OR NOT coalesce(erev.entity_in_scope(NEW.entity_id), false) THEN
    RETURN NEW;
  END IF;
  SELECT s.state::text INTO period_state_now
    FROM erev.period_state s
   WHERE s.tenant_id = NEW.tenant_id AND s.entity_id = NEW.entity_id
     AND s.book_code = NEW.book_code AND s.period_id = NEW.period_id;
  IF period_state_now IS NULL OR period_state_now NOT IN ('open', 'closing', 'reopened') THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-003: period %s of entity %s is %s in book %s, so journal line %s '
                       'cannot post into it', NEW.period_id, NEW.entity_id,
                       coalesce(period_state_now, 'without a state'), NEW.book_code, NEW.id);
  END IF;
  RETURN NEW;
END
"""

# T-CLS-04 (04 rev 1.113): a cutoff on a LOCK row and on no other kind.
CUTOFF_CHECK_SQL: Final = "(kind = 'LOCK') = (cutoff_known_at IS NOT NULL)"

# DG-MIG-13: the validation scans every physical row whatever row-level security hides from the
# owner connection. A constant statement (no interpolation). A LOCK row of an earlier pre-release
# schema has no cutoff: the check_violation is caught INSIDE the block, so the constraint stays
# NOT VALID — enforced for every new row — and the revision continues; nothing is rewritten.
VALIDATE_CUTOFF_CHECK: Final = """
DO $$
BEGIN
  ALTER TABLE erev.period_lock VALIDATE CONSTRAINT ck_period_lock__cutoff_known_at;
EXCEPTION
  WHEN check_violation THEN
    RAISE NOTICE 'EREV-MIG-0084: period_lock holds LOCK rows written before revision 0084; they '
                 'keep a NULL cutoff_known_at and ck_period_lock__cutoff_known_at stays NOT VALID '
                 '(it is enforced for every row written from this revision on)';
END
$$;
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
    """The two guards first, then the lock's cutoff column with its check."""
    _replace_function(SUBLEDGER_GUARD, SUBLEDGER_GUARD_BODY)
    _replace_function(JOURNAL_GUARD, JOURNAL_GUARD_BODY)
    ops.execute(f"ALTER TABLE {LOCK_TABLE} ADD COLUMN {CUTOFF_COLUMN} timestamptz NULL")
    ops.execute(
        f"ALTER TABLE {LOCK_TABLE} ADD CONSTRAINT {CUTOFF_CHECK} "
        f"CHECK ({CUTOFF_CHECK_SQL}) NOT VALID"
    )
    ops.execute(VALIDATE_CUTOFF_CHECK)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order, and restore the two previous
    bodies verbatim (DG-MIG-04)."""
    ops.execute(f"ALTER TABLE {LOCK_TABLE} DROP CONSTRAINT {CUTOFF_CHECK}")
    ops.execute(f"ALTER TABLE {LOCK_TABLE} DROP COLUMN {CUTOFF_COLUMN}")
    _replace_function(JOURNAL_GUARD, JOURNAL_GUARD_BODY_0046)
    _replace_function(SUBLEDGER_GUARD, SUBLEDGER_GUARD_BODY_0040)
