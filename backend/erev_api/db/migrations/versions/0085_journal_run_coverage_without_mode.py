"""Security finding SC-7 (supervisor ruling R-32; 04 rev 1.106 DB-16 and T-SL-06 keys note;
ENGINE_SPEC_B rev 1.54 S14-R-16 / S14-INV-07): journal-run coverage without the mode.

``tg_journal_run__coverage`` (installed by 0046, CLO-1) keyed the coverage of a run on
(entity, book, period, mode): the advisory lock and the covered maximum each named the mode, so a
``DELTA`` run started at chain sequence 0 beside a ``GROSS`` run and journalised the same seals
again (a ``DELTA`` run outputs the primary-book lines a ``GROSS`` run outputs plus the LEGACY
lines, S14-R-23). This revision replaces the body of the function with ``CREATE OR REPLACE
FUNCTION`` (the 0065 / 0069 / 0070 precedent: grants and the trigger are kept):

- the advisory lock and the covered maximum are keyed on (tenant, entity, book, period);
- a run that states a LEGACY range starts it at the maximum ``delta_to_chain_seq`` of the key's
  non-cancelled runs, or 0 — the same rule for the second book a ``DELTA`` run covers.

``EREV-JR-001`` is unchanged. The downgrade restores the 0046 literal verbatim (DG-MIG-04). No
table, column, type or function is added (the erev function count is unchanged). A revision imports
nothing of ``erev_api`` beyond the DDL helpers (DG-MIG-12): both bodies are literals.
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0085"
down_revision = "0093"
branch_labels = None
depends_on = None

FUNCTION: Final = "tg_journal_run__coverage"

# DB-16 (04 rev 1.106): the non-cancelled runs of one (entity, book, period) cover contiguous seal
# ranges from 0, whatever their mode, and so do their LEGACY ranges. The transaction-level advisory
# lock on that key serialises the writers of its runs, so each sees the runs the others committed.
BODY: Final = """
DECLARE
  covered bigint;
  legacy_covered bigint;
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id()
     OR NOT coalesce(erev.entity_in_scope(NEW.entity_id), false) THEN
    RETURN NEW;
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(
    'erev.journal_run:' || NEW.tenant_id::text || ':' || NEW.entity_id::text || ':'
    || NEW.book_code::text || ':' || NEW.period_id::text, 0));
  SELECT coalesce(max(r.to_chain_seq), 0), coalesce(max(r.delta_to_chain_seq), 0)
    INTO covered, legacy_covered
    FROM erev.journal_run r
   WHERE r.tenant_id = NEW.tenant_id AND r.entity_id = NEW.entity_id
     AND r.book_code = NEW.book_code AND r.period_id = NEW.period_id
     AND r.state <> 'cancelled' AND r.id <> NEW.id;
  IF NEW.from_chain_seq IS DISTINCT FROM covered THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-JR-001: run %s starts at chain sequence %s, but the runs of '
                       'entity %s, book %s and period %s cover up to %s', NEW.run_no,
                       NEW.from_chain_seq, NEW.entity_id, NEW.book_code, NEW.period_id, covered);
  END IF;
  IF NEW.delta_from_chain_seq IS NOT NULL
     AND NEW.delta_from_chain_seq IS DISTINCT FROM legacy_covered THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-JR-001: run %s starts its LEGACY range at chain sequence %s, but '
                       'the runs of entity %s, book %s and period %s cover the LEGACY book up to '
                       '%s', NEW.run_no, NEW.delta_from_chain_seq, NEW.entity_id, NEW.book_code,
                       NEW.period_id, legacy_covered);
  END IF;
  RETURN NEW;
END
"""

# The 0046 literal, verbatim (DG-MIG-04).
PREVIOUS: Final = """
DECLARE
  covered bigint;
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id()
     OR NOT coalesce(erev.entity_in_scope(NEW.entity_id), false) THEN
    RETURN NEW;
  END IF;
  PERFORM pg_advisory_xact_lock(hashtextextended(
    'erev.journal_run:' || NEW.tenant_id::text || ':' || NEW.entity_id::text || ':'
    || NEW.book_code::text || ':' || NEW.period_id::text || ':' || NEW.mode::text, 0));
  SELECT coalesce(max(r.to_chain_seq), 0) INTO covered
    FROM erev.journal_run r
   WHERE r.tenant_id = NEW.tenant_id AND r.entity_id = NEW.entity_id
     AND r.book_code = NEW.book_code AND r.period_id = NEW.period_id AND r.mode = NEW.mode
     AND r.state <> 'cancelled' AND r.id <> NEW.id;
  IF NEW.from_chain_seq IS DISTINCT FROM covered THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-JR-001: run %s starts at chain sequence %s, but the runs of '
                       'entity %s, book %s, period %s and mode %s cover up to %s', NEW.run_no,
                       NEW.from_chain_seq, NEW.entity_id, NEW.book_code, NEW.period_id, NEW.mode,
                       covered);
  END IF;
  RETURN NEW;
END
"""


def _replace_function(body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger (NC-18 attributes)."""
    if "$fn$" in body:
        raise ValueError("a trigger function body must not contain $fn$")
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.{FUNCTION}() RETURNS trigger "
        f"LANGUAGE plpgsql SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def upgrade() -> None:
    _replace_function(BODY)


def downgrade() -> None:
    """Restore exactly the previous body, verbatim (DG-MIG-04)."""
    _replace_function(PREVIOUS)
