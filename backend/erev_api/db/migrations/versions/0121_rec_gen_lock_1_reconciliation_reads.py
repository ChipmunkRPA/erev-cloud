"""Item REC-GEN-LOCK-1 (the supervisor's rulings of 2026-10-01 21:41 and 22:52 and of 2026-10-02
00:09 and 01:41, replacing the lock of ruling R-68 (b); 04 rev 1.259; number assigned by the
supervisor, register index 211): what a reconciliation READ, on T-CLS-06 ``reconciliation`` —
three nullable columns.

- ``ledger_chain_seq`` (bigint, NULL): the book's ledger chain position (T-SL-03
  ``last_chain_seq``) as the generation read it. A seal takes the chain head's row lock and holds
  it to commit, so the chain sequence is the commit order of the book's postings: a posting is in
  the reconciliation exactly when its seal is not later.
- ``source_documents_read`` (integer, NULL): for billing to subledger, the number of source
  invoices of the entity issued in the period that the generation read, every stored version.
- ``subledger_documents_read`` (integer, NULL): what the generation depends on beside the
  ledger, as a number of rows. Billing to subledger: of the contracts that hold a billing event
  dated in the period, the billing events dated on or before the period's last day and the
  voids of any date. Subledger to GL: the contract events of the entity's contracts dated on or
  before the period's last day, plus the number of times a contract version of the book
  includes one of them (T-CON-08 ``cause_event_ids``) — an event moves the number when it is
  recorded and again when it is first computed into the book. A generation counts the rows at
  or before its own ``as_of_known_at``, which is what its attach reads; the gate counts every
  row there is.

A reviewed reconciliation is out of date when a line of its scope was sealed after its position
or a number differs now (``erev_api.domain.close.gates.overtaken``). The columns replace a test by
time — a line recorded after ``as_of_known_at`` — which cannot see a posting that began before a
generation and committed after it: a line's ``recorded_at`` is the start of its unit of work. A
row generated before this revision holds NULL in all three and keeps that earlier test.

None of the three is updatable: they are written by the INSERT of the generation, the IM-S
column list of the table is unchanged, and so the DB-03 function
``tg_reconciliation__transition()`` and the column grants of ``erev_app`` stay as they are. No
table, type, constraint or function is added (the erev function count is unchanged); no row is
written (DG-MIG-07).

The downgrade drops the three columns and refuses no row (DG-MIG-04): the application of the
earlier revision reads none of them, and a reconciliation generated under this revision falls
back to the time test with the rest. ``down_revision`` is revision 0119 of the same lane, which
this revision was built on (supervisor ruling R-68 (e): the chain follows merge order).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0121"
down_revision = "0119"
branch_labels = None
depends_on = None

TABLE: Final = "reconciliation"
# (column, type) in the order they are added; dropped in reverse.
COLUMNS: Final = (
    ("ledger_chain_seq", "bigint"),
    ("source_documents_read", "integer"),
    ("subledger_documents_read", "integer"),
)


def upgrade() -> None:
    for name, kind in COLUMNS:
        ops.execute(f"ALTER TABLE erev.{TABLE} ADD COLUMN {name} {kind} NULL")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    for name, _ in reversed(COLUMNS):
        ops.execute(f"ALTER TABLE erev.{TABLE} DROP COLUMN {name}")
