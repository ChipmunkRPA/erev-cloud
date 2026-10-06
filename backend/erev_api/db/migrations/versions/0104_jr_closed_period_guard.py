"""Item JR-CLOSED-PERIOD-GUARD-1 (supervisor ruling R-97 (7) of 2026-09-30 on gap G2 of the
independent review of revision 0084; 04 rev 1.205 §14.1 DB-07 and DB-16; 05 rev 1.144; PRD rev
1.134 ERR-86) with the line guard of supervisor ruling R-112 (b) (6) (independent security review,
finding N2 (b)). Two triggers, each over a new function; no table, column, type or grant changes.

- DB-07 ``tg_journal_run__period_guard`` (``BEFORE INSERT OR UPDATE OF state`` on T-SL-06
  ``journal_run``): a run is neither inserted nor moved to ``cancelled`` while the period of its
  entity and book is ``closed`` or ``permanently_locked`` (``EREV-LED-003``). The guard reads the
  period's state row ``FOR SHARE``, as the two line guards do, so the lock decision — which holds
  that row ``FOR UPDATE`` from its first read, before its gates — waits for a calculation or a
  cancel in flight and sees it, and one that arrives later waits and is refused. Until now a run
  had no period read of its own: a run without lines could be calculated into a locked period,
  the only run of a period could be cancelled after — or beside — its lock, and the decision's
  count of runs was a check where it now states an invariant. Any other change of a run's state
  is left alone: a period locks with every batch acknowledged or under a waiver of that gate,
  and what a batch of a closed period then still takes — the retry, the hand-over, the
  acknowledgement — completes the export of the population the lock certified (PRD SM-08 rev
  1.167).
- DB-16 ``tg_journal_line__batch_draft`` (``BEFORE INSERT`` on T-SL-09 ``journal_line``): a line
  joins a batch only while the batch is ``draft`` (``EREV-JE-003``). ``journal_line`` is IM-A, so
  an insert is the only way a batch's lines can change; the approval of a run covers each batch's
  stored count and totals, and a line that reached an approved batch changed what would leave and
  none of those figures. The guard reads the batch row ``FOR SHARE``: an approval waits for a line
  in flight and its DB-16 balance check counts it, and a line that arrives later is refused. The
  recount at every exit of a batch (ADP-31) stays as the layer behind it.

Both guards return ``NEW`` for a row outside the session's tenant or entity scope, as the DB-07
line guards do: row-level security refuses such a row. The erev function count grows by two. The
downgrade drops both triggers and both functions.

Revision 0104, assigned by the supervisor (04 §18 rule 9); ``down_revision`` is main's head at the
lane's merges of main (0111 at 4050c50d, 0094 at ac5e337b, 0114 at a978ba29; supervisor
ruling R-68 (e)) and is re-pointed when another lane's revision lands first. A revision imports
nothing of ``erev_api`` beyond the DDL helpers (DG-MIG-12): both bodies are literals.
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0104"
down_revision = "0114"
branch_labels = None
depends_on = None

# DB-07 for T-SL-06: a run is neither calculated nor cancelled in a closed period.
RUN_PERIOD_GUARD_BODY: Final = """
DECLARE
  period_state_now text;
BEGIN
  IF TG_OP = 'UPDATE' AND (NEW.state::text <> 'cancelled' OR OLD.state::text = 'cancelled') THEN
    RETURN NEW;
  END IF;
  IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id()
     OR NOT coalesce(erev.entity_in_scope(NEW.entity_id), false) THEN
    RETURN NEW;
  END IF;
  SELECT s.state::text INTO period_state_now
    FROM erev.period_state s
   WHERE s.tenant_id = NEW.tenant_id AND s.entity_id = NEW.entity_id
     AND s.book_code = NEW.book_code AND s.period_id = NEW.period_id
     FOR SHARE;
  IF period_state_now IN ('closed', 'permanently_locked') THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-LED-003: period %s of entity %s is %s in book %s, so journal run %s '
                       'cannot be %s in it', NEW.period_id, NEW.entity_id, period_state_now,
                       NEW.book_code, NEW.id,
                       CASE WHEN TG_OP = 'INSERT' THEN 'calculated' ELSE 'cancelled' END);
  END IF;
  RETURN NEW;
END
"""

# DB-16 for T-SL-09: a line joins a batch only while the batch is draft.
LINE_BATCH_DRAFT_BODY: Final = """
DECLARE
  batch_state text;
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id()
     OR NOT coalesce(erev.entity_in_scope(NEW.entity_id), false) THEN
    RETURN NEW;
  END IF;
  SELECT b.state::text INTO batch_state
    FROM erev.journal_batch b
   WHERE b.tenant_id = NEW.tenant_id AND b.id = NEW.journal_batch_id
     FOR SHARE;
  IF batch_state IS DISTINCT FROM 'draft' THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-JE-003: journal batch %s is %s, so journal line %s cannot join it: '
                       'a batch takes lines only while it is draft', NEW.journal_batch_id,
                       coalesce(batch_state, 'not visible'), NEW.id);
  END IF;
  RETURN NEW;
END
"""


def upgrade() -> None:
    """Add the DB-07 guard of ``journal_run`` and the DB-16 guard of ``journal_line``."""
    ops.create_trigger(
        "journal_run",
        "period_guard",
        RUN_PERIOD_GUARD_BODY,
        timing="BEFORE",
        events="INSERT OR UPDATE OF state",
    )
    ops.create_trigger(
        "journal_line", "batch_draft", LINE_BATCH_DRAFT_BODY, timing="BEFORE", events="INSERT"
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created."""
    ops.execute("DROP TRIGGER tg_journal_line__batch_draft ON erev.journal_line")
    ops.execute("DROP FUNCTION erev.tg_journal_line__batch_draft()")
    ops.execute("DROP TRIGGER tg_journal_run__period_guard ON erev.journal_run")
    ops.execute("DROP FUNCTION erev.tg_journal_run__period_guard()")
