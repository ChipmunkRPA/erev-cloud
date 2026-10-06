"""Lane SECFIX-PLT, item COMPUTE-BEHIND-CUTOFF-1 — PRODUCT DEFECT, a release blocker (the limit
of clause (iii) of item COMPUTE-BEHIND-GROUP-1, measured by lane ENG-FX and by this lane; the
supervisor's order of 2026-10-02 19:47 on lane ENG-FX's line; 04 rev 1.302 T-CON-07 and §14.1;
number assigned by the supervisor, register index 285): the cutoff a computation's bundle
admitted by.

``contract_computation.cutoff_at`` holds the record-time cutoff of the bundle the computation
stored — the later of its unit of work's instant and its transaction's start
(``bundles.record_cutoff``; 05 RCP-15): the bound the bundle admitted events, marks and versions
by. ``computation.behind_its_group`` compares the group's head with a bundle by that bound.
Until this revision it compared the head's ``created_at``, the instant of its unit of work on the
application's clock, and where that clock ran behind the database's a computation whose cutoff
lay between a head's instant and the head's own bound was stored and posted the head's
difference back out (measured with the clock twenty seconds behind: GBP 540.00).

A computation stored before this revision has no cutoff — the column's NULL — and none is
written for it: the value is kept nowhere (the row's ``known_at`` is the latest ``recorded_at``
of its events, not the bound). Such a head is read by its ``created_at``, as before, until its
group is computed again.

One nullable column, no default, no check, no index and no function. T-CON-07 is IM-A: the app
role holds INSERT on the table and no column grant, so no grant is added, and
``tg_forbid_mutation`` keeps a stored cutoff as it keeps the row. The table is not carried by a
tenant snapshot (a loaded sandbox computes for itself). The downgrade drops the column; no row
is rewritten in either direction.

Revision 0129 on the head named below: 0130, the integration branch's head at the supervisor's
merge of this head. It was written on 0123, that branch's head at the lane's build (supervisor
ruling R-68 (e): a revision keeps its number and follows the head it finds, so the chain is in
merge order).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0129"
down_revision = "0130"
branch_labels = None
depends_on = None

TABLE: Final = "contract_computation"


def upgrade() -> None:
    ops.execute(f"ALTER TABLE erev.{TABLE} ADD COLUMN cutoff_at timestamptz")


def downgrade() -> None:
    """Remove exactly what upgrade() created (DG-MIG-04)."""
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP COLUMN cutoff_at")
