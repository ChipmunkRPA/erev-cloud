"""Lane SECFIX-APR, item SSP-ENTITY-SCOPE-1 (supervisor ruling R-28, row N-29 of the ruled
repairs; 04 rev 1.277 T-REF-32; number assigned by the supervisor, register index 234): the scope
of an SSP calculator run.

``ssp_calculator_run.entity_ids`` holds the entities the run's provider was allowed to read — the
requester's ``contract.read`` scope at the request: NULL for every entity, the named set
otherwise, never empty (``ck_ssp_calculator_run__entity_ids``). It is the shape of T-IMP-02
``named_entity_ids``, and for the same reason: the set is a requirement — a reader's
``contract.read`` covers EVERY element — so its unresolved form is NULL, which a holder for all
entities alone reads (supervisor ruling R-98; ``snapshot_dataset.SCOPE_ARRAYS``). The job runs as
SYSTEM, so the scope is known only while the request that creates the run runs; the column keeps
it, the provider is limited to it and every later read and command asks it
(``domain/ssp/calculator.py``).

A run stored before this revision reads as a run of every entity — the column's NULL: its
provider read every entity. No result file is read again (D-99).

The column is written at INSERT and never again: it is outside the updatable column list of the
DB-03 function ``tg_ssp_calculator_run__transition()`` (``erev_api.db.transitions``), which
refuses a change to any column it does not name, and the app role holds no column UPDATE grant on
it. So no function is replaced, no grant is added and the installed function source stays the
fresh rendering (DG-ARC-07). The downgrade drops the check and the column; no row is rewritten.

Revision 0123 on the head named below: main's head at the lane's merge (supervisor ruling R-68
(e): a revision keeps its number and follows main's head, so the chain is in merge order).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0123"
down_revision = "0110"
branch_labels = None
depends_on = None

TABLE: Final = "ssp_calculator_run"
CHECK: Final = "ck_ssp_calculator_run__entity_ids"


def upgrade() -> None:
    ops.execute(f"ALTER TABLE erev.{TABLE} ADD COLUMN entity_ids uuid[]")
    ops.execute(
        f"ALTER TABLE erev.{TABLE} ADD CONSTRAINT {CHECK} "
        "CHECK (entity_ids IS NULL OR cardinality(entity_ids) > 0)"
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created (DG-MIG-04)."""
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP CONSTRAINT {CHECK}")
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP COLUMN entity_ids")
