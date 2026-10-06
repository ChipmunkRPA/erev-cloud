"""Lane ENG-FX, item ENG-COST-READBACK-1 (supervisor ruling R-11 as amended on 2026-10-02; number
assigned by the supervisor).

04 id amended (rev 1.282): T-SL-04 ``subledger_line`` gains ``subject_key`` (text, nullable) — the
subject of the entry a line belongs to, as the engine keys it (``PostingIntent.subject_key``;
ENGINE_SPEC_B S14-R-12). ``journals.subledger.post`` requires it of every product caller and the
RCP-05 read-back answers it (05 RCP-05 rev 1.202). Until this revision the read-back spelled
every line without an obligation ``<contract>@<entity>`` (decision L3-1-Q-32), so each
computation after the first took the lines of a cost asset, a refund-liability component and a
contract-level loss unit back under that spelling and posted them again under their own subject
(ENGINE_SPEC_B S14-R-04 rev 1.165, S14-INV-02); behind a lock those lines carried no source
event and the next close run stopped at its dataset freeze (S15-R-18b).

One column on the partitioned parent of 0040, which reaches the partitions with it; no table,
enum type, function, trigger, index or grant. The IM-A triggers of 0040 forbid UPDATE and DELETE,
so the column is immutable with its row, and the table-level SELECT and INSERT grants of the class
cover it. The column is nullable: a line a test builder writes stores no key and reads back in the
spelling of L3-1-Q-32; NOT NULL is a later revision (the ruling's point 4).

Rows written before this revision. Nothing is backfilled, and the revision REFUSES a table that
already holds a line (``EREV-MIG-0124``): the subject of a posted line cannot be derived
from its row; a revision runs on the owner connection without a tenant context and sees no tenant
row under the forced policy; T-SL-04 is IM-A, so a sealed line is never rewritten; and the key is
inside the sealed line document (``subledger.LINE_MEMBERS``), so writing it would break the seal
of every earlier posting — as would leaving it empty, since the document gains a member. The
refusal is asked through a constraint's validation scan, which reads every physical row whatever
row-level security hides (dev-guide DG-MIG-13): ``CHECK (subject_key IS NOT NULL)`` is added and
dropped again; it fails exactly when a row exists, and only that ``check_violation`` is turned
into the named refusal, which propagates so that the whole revision rolls back. Its sentence
says what the person does next: no workspace is deployed (01-DECISIONS D-99 (3)), so a
development database that holds ledger lines is reset and seeded anew; the demo and performance
seeds, a sandbox copy and a snapshot load produce their ledgers through the product's writers, so
their lines carry the key. This is the revision an earlier pre-release ledger cannot cross
(dev-guide DG-MIG-13).

The downgrade drops the column (DG-MIG-04). Revision 0124 on 0129, the integration branch's
head at the supervisor's merge of this head; it was written on 0104, main's head at the lane's
merge of main (supervisor ruling R-68 (e): a revision keeps its number and follows the head it
finds, so the chain is in merge order). A revision imports nothing of ``erev_api`` beyond the
DDL helpers (DG-MIG-12).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0124"
down_revision = "0129"
branch_labels = None
depends_on = None

TABLE: Final = "erev.subledger_line"
COLUMN: Final = "subject_key"

# DG-MIG-13: the validation scans every physical row whatever row-level security hides from the
# owner connection. A constant statement (no interpolation). Every existing row holds NULL in the
# new column, so the check fails exactly when the table holds a row; only that check_violation is
# translated, and the RAISE propagates: the revision's transaction rolls back, the column
# included. Nothing is written, deleted or rewritten; RLS and roles are untouched.
REFUSE_A_POPULATED_TABLE: Final = """
DO $$
BEGIN
  ALTER TABLE erev.subledger_line
    ADD CONSTRAINT ck_subledger_line__subject_key_probe CHECK (subject_key IS NOT NULL);
  ALTER TABLE erev.subledger_line DROP CONSTRAINT ck_subledger_line__subject_key_probe;
EXCEPTION
  WHEN check_violation THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'EREV-MIG-0124: subledger_line holds lines written before revision 0124; the '
                'subject key of a posted line cannot be derived and a sealed line is never '
                'rewritten. A pre-release ledger does not cross this revision (01-DECISIONS '
                'D-99 (3)): reset the database and seed it anew';
END
$$;
"""


def upgrade() -> None:
    """Add the T-SL-04 subject key to the partitioned parent; refuse a table that holds a line."""
    ops.execute(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} text NULL")
    ops.execute(REFUSE_A_POPULATED_TABLE)


def downgrade() -> None:
    """Remove exactly what upgrade() created (DG-MIG-04)."""
    ops.execute(f"ALTER TABLE {TABLE} DROP COLUMN {COLUMN}")
