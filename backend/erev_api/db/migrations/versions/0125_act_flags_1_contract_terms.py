"""Lane FIX-D2, item ACT-FLAGS-1 (register index 260; the supervisor's rulings of 2026-10-02 on
the lane's pre-build line; 04 rev 1.287 T-CON-01, §16.3 ``CONTRACT_BOOKED``, §16.10; PRD rev 1.194
§2.5): what a booking states of two terms no other member of the record holds.

- T-CON-01 ``contract.acceptance_clause`` — ``boolean NULL``: the contract holds a customer
  acceptance clause;
- T-CON-01 ``contract.side_letter`` — ``boolean NULL``: a side letter exists beside the contract.

Each is true, false or NULL — "the booking did not state it". The header projection writes them
from the ``CONTRACT_BOOKED`` payload, at a booking and at a draft's replacement; the routing flags
of the contract's activation read them (``domain.contracts.activation.routing_facts``): true gives
``NON_STANDARD_TERMS`` or ``SIDE_LETTER``, NULL gives ``TERMS_NOT_STATED``, and any flag withholds
the activation from the auto-approval rules.

No backfill and no default: every contract that exists did not state the two terms, and NULL
says so. A request that is pending at the upgrade keeps the flags it was routed with — a decision
does not read them again. The columns join the table after its standard columns. ``contract`` is
IM-X: ``erev_app`` holds UPDATE on the table, so no column grant is added, and the DB-18
``tg_contract__projection`` compares every column that is not on its list, so the two change only
in the transaction that appends an event, as the other header members do. No table, type,
function, trigger, index or grant is added.

The downgrade drops the two columns (DG-MIG-04). What bookings stated of the two terms stays in
their ``CONTRACT_BOOKED`` payloads — the stream is append-only — and the payload model of the
earlier revision forbids a member it does not know: a booking that stated a term is not read by
the application of that revision. The module imports ``migration_ops`` only (DG-MIG-12).

Revision 0125, assigned by the supervisor (04 §18 rule 9). ``down_revision`` was 0117, main's
head at this lane's merge of main a101c4c0, and is 0123, the integration branch's head at the
supervisor's merge (ruling R-68 (e)).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0125"
down_revision = "0123"
branch_labels = None
depends_on = None

TABLE: Final = "contract"
COLUMNS: Final = ("acceptance_clause", "side_letter")


def upgrade() -> None:
    for column in COLUMNS:
        ops.execute(f"ALTER TABLE erev.{TABLE} ADD COLUMN {column} boolean")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    for column in reversed(COLUMNS):
        ops.execute(f"ALTER TABLE erev.{TABLE} DROP COLUMN {column}")
