"""CLO-CANCEL-CLOSE-REOPENED-1 (PRD rev 1.99 SM-07, BR-CLS-06; 04 rev 1.170 T-REF-07, table 3.4-R
and §16.8): the pair ``closing → reopened``.

``cancel-close`` returned every period in soft close to ``open``. A period that had been locked and
reopened then read ``open`` after ``reopened → closing → open``: the DB-07 guards stored
``is_post_reopen = false`` on its later lines and the posting commands stopped asking for the human
approval of BR-CLS-06. The end of a soft close now returns such a period to ``reopened``, which
needs the pair in the database:

- ``tg_period_state__update`` and ``tg_period_state_transition__pair`` (installed by 0029) admit
  ``closing → reopened``. Both bodies are replaced with ``CREATE OR REPLACE FUNCTION`` (the 0065 /
  0069 / 0070 / 0085 precedent: grants and triggers are kept); nothing else in them changes.
- The three checks of T-REF-07 follow. ``ck_period_state_transition__reason_code``: the pair
  carries a reason of the cancel subset, as ``closing → open`` does.
  ``ck_period_state_transition__approval`` and ``ck_period_state_transition__lock``: the pair
  names neither an approval request nor a lock record — the end of a soft close approves nothing
  and writes no ``period_lock`` row — while ``closed → reopened`` and the other approved targets
  keep requiring both.

The downgrade restores the 0029 literals verbatim (DG-MIG-04). It needs a table without a
``closing → reopened`` row: the restored checks would refuse such a row, so ``ADD CONSTRAINT``
fails by name and the downgrade stops there (DG-MIG-06). No table, column, type or function is
added (the erev function count is unchanged). A revision imports nothing of ``erev_api`` beyond
the DDL helpers (DG-MIG-12): every body and check is a literal.
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0107"
down_revision = "0101"
branch_labels = None
depends_on = None

TABLE: Final = "period_state_transition"
UPDATE_FUNCTION: Final = "tg_period_state__update"
PAIR_FUNCTION: Final = "tg_period_state_transition__pair"
REASON_CHECK: Final = "ck_period_state_transition__reason_code"
APPROVAL_CHECK: Final = "ck_period_state_transition__approval"
LOCK_CHECK: Final = "ck_period_state_transition__lock"

_CANCEL_REASONS: Final = "'CLOSE_RESTARTED', 'DATA_CORRECTION_PENDING', 'OTHER'"
_REOPEN_REASONS: Final = "'ERROR_CORRECTION', 'LATE_SOURCE_DATA', 'AUDIT_ADJUSTMENT', 'OTHER'"
_APPROVED_STATES: Final = "'closed', 'reopened', 'permanently_locked'"
# The end of a soft close of a period that has been locked before. ``from_state`` is NULL on the
# creation row, hence IS NOT DISTINCT FROM: the term is never NULL.
_RETURN: Final = "(from_state IS NOT DISTINCT FROM 'closing' AND to_state = 'reopened')"

# DB-07 (04 rev 1.170): 0029's body with the pair ``closing>reopened`` added to the allowed pairs.
UPDATE_BODY: Final = """
BEGIN
  IF NEW.entity_id IS DISTINCT FROM OLD.entity_id OR NEW.book_code IS DISTINCT FROM OLD.book_code
     OR NEW.period_id IS DISTINCT FROM OLD.period_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-PER-001: the entity, book and period of %I.%I row %s cannot change',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.id);
  END IF;
  IF NEW.state IS NOT DISTINCT FROM OLD.state THEN
    RETURN NEW;
  END IF;
  IF (OLD.state::text || '>' || NEW.state::text) <> ALL (ARRAY[
       'future>open', 'open>closing', 'closing>open', 'closing>reopened', 'closing>closed',
       'closed>reopened', 'reopened>closing', 'closed>permanently_locked']) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-PER-001: %I.%I row %s cannot move from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.id, OLD.state, NEW.state);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM erev.period_state_transition t
     WHERE t.tenant_id = NEW.tenant_id AND t.period_state_id = NEW.id
       AND t.created_txid = txid_current()
       AND t.from_state = OLD.state AND t.to_state = NEW.state
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-PER-001: %I.%I row %s moved from %s to %s without a transition',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.id, OLD.state, NEW.state);
  END IF;
  RETURN NEW;
END
"""

# DB-07 with T-REF-07 (04 rev 1.170): 0029's body with the pair added.
PAIR_BODY: Final = """
BEGIN
  IF (coalesce(NEW.from_state::text, '') || '>' || NEW.to_state::text) <> ALL (ARRAY[
       '>future', 'future>open', 'open>closing', 'closing>open', 'closing>reopened',
       'closing>closed', 'closed>reopened', 'reopened>closing', 'closed>permanently_locked']) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-PER-001: %I.%I allows no transition from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, coalesce(NEW.from_state::text, 'NULL'),
                       NEW.to_state);
  END IF;
  RETURN NEW;
END
"""

# T-REF-07 ``reason_code``: 0029's two terms, and the cancel subset for the new pair. The new term
# is strict: a NULL reason is refused (``NULL IN (…)`` is NULL, which a CHECK lets pass — as the
# two 0029 terms do, unchanged here: the commands require the reason of those pairs).
REASON_SQL: Final = (
    "(NOT (from_state = 'closing' AND to_state = 'open') "
    f"OR reason_code IN ({_CANCEL_REASONS})) "
    "AND (NOT (from_state = 'closing' AND to_state = 'reopened') "
    f"OR coalesce(reason_code IN ({_CANCEL_REASONS}), false)) "
    "AND (NOT (from_state = 'closed' AND to_state = 'reopened') "
    f"OR reason_code IN ({_REOPEN_REASONS}))"
)
# T-REF-07 ``approval_request_id`` and ``period_lock_id``: required into the approved states, and
# NULL on the row that ends a soft close in ``reopened``.
APPROVAL_SQL: Final = (
    f"({_RETURN} AND approval_request_id IS NULL) OR (NOT {_RETURN} "
    f"AND (to_state NOT IN ({_APPROVED_STATES}) OR approval_request_id IS NOT NULL))"
)
LOCK_SQL: Final = (
    f"({_RETURN} AND period_lock_id IS NULL) OR (NOT {_RETURN} "
    f"AND (to_state NOT IN ({_APPROVED_STATES}) OR period_lock_id IS NOT NULL))"
)

# The 0029 literals, verbatim (the downgrade).
PREVIOUS_UPDATE_BODY: Final = """
BEGIN
  IF NEW.entity_id IS DISTINCT FROM OLD.entity_id OR NEW.book_code IS DISTINCT FROM OLD.book_code
     OR NEW.period_id IS DISTINCT FROM OLD.period_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-PER-001: the entity, book and period of %I.%I row %s cannot change',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.id);
  END IF;
  IF NEW.state IS NOT DISTINCT FROM OLD.state THEN
    RETURN NEW;
  END IF;
  IF (OLD.state::text || '>' || NEW.state::text) <> ALL (ARRAY[
       'future>open', 'open>closing', 'closing>open', 'closing>closed', 'closed>reopened',
       'reopened>closing', 'closed>permanently_locked']) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-PER-001: %I.%I row %s cannot move from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.id, OLD.state, NEW.state);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM erev.period_state_transition t
     WHERE t.tenant_id = NEW.tenant_id AND t.period_state_id = NEW.id
       AND t.created_txid = txid_current()
       AND t.from_state = OLD.state AND t.to_state = NEW.state
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-PER-001: %I.%I row %s moved from %s to %s without a transition',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.id, OLD.state, NEW.state);
  END IF;
  RETURN NEW;
END
"""

PREVIOUS_PAIR_BODY: Final = """
BEGIN
  IF (coalesce(NEW.from_state::text, '') || '>' || NEW.to_state::text) <> ALL (ARRAY[
       '>future', 'future>open', 'open>closing', 'closing>open', 'closing>closed',
       'closed>reopened', 'reopened>closing', 'closed>permanently_locked']) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-PER-001: %I.%I allows no transition from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, coalesce(NEW.from_state::text, 'NULL'),
                       NEW.to_state);
  END IF;
  RETURN NEW;
END
"""

PREVIOUS_REASON_SQL: Final = (
    "(NOT (from_state = 'closing' AND to_state = 'open') "
    "OR reason_code IN ('CLOSE_RESTARTED', 'DATA_CORRECTION_PENDING', 'OTHER')) "
    "AND (NOT (from_state = 'closed' AND to_state = 'reopened') "
    "OR reason_code IN ('ERROR_CORRECTION', 'LATE_SOURCE_DATA', 'AUDIT_ADJUSTMENT', "
    "'OTHER'))"
)
PREVIOUS_APPROVAL_SQL: Final = (
    f"to_state NOT IN ({_APPROVED_STATES}) OR approval_request_id IS NOT NULL"
)
PREVIOUS_LOCK_SQL: Final = f"to_state NOT IN ({_APPROVED_STATES}) OR period_lock_id IS NOT NULL"


def _replace_function(name: str, body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger (NC-18 attributes)."""
    if "$fn$" in body:
        raise ValueError("a trigger function body must not contain $fn$")
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.{name}() RETURNS trigger "
        f"LANGUAGE plpgsql SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def _replace_check(name: str, expression: str) -> None:
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP CONSTRAINT {name}")
    ops.execute(f"ALTER TABLE erev.{TABLE} ADD CONSTRAINT {name} CHECK ({expression})")


def upgrade() -> None:
    _replace_function(UPDATE_FUNCTION, UPDATE_BODY)
    _replace_function(PAIR_FUNCTION, PAIR_BODY)
    _replace_check(REASON_CHECK, REASON_SQL)
    _replace_check(APPROVAL_CHECK, APPROVAL_SQL)
    _replace_check(LOCK_CHECK, LOCK_SQL)


def downgrade() -> None:
    """Restore exactly the 0029 checks and bodies, verbatim (DG-MIG-04). With a ``closing →
    reopened`` row in the table the restored lock check refuses it: ``ADD CONSTRAINT`` fails and
    the revision's transaction rolls back, so nothing is changed."""
    _replace_check(LOCK_CHECK, PREVIOUS_LOCK_SQL)
    _replace_check(APPROVAL_CHECK, PREVIOUS_APPROVAL_SQL)
    _replace_check(REASON_CHECK, PREVIOUS_REASON_SQL)
    _replace_function(PAIR_FUNCTION, PREVIOUS_PAIR_BODY)
    _replace_function(UPDATE_FUNCTION, PREVIOUS_UPDATE_BODY)
