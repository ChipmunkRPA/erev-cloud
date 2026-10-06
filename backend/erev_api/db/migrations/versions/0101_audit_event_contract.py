"""Lane API-GAPS, item AUD-API-GAPS-1 (supervisor rulings R-108 and R-114; table id and number
assigned by the supervisor): T-PLT-48 ``audit_event_contract``, the index of the contract key of an
audit event (04 T-PLT-48 and T-PLT-19 "Contract key", rev 1.154).

Since rev 1.154 an event of an object that belongs to a contract names the contract in ``detail``
(``contract_id``, or ``contract_ids`` for several). ``GET /audit-events?contract_id=`` reads the
events of one contract without a range of ``occurred_at``, so it needs an index — and no index
over ``detail`` can give it one: ``audit_event`` carries a row-level-security policy, and under a
policy PostgreSQL turns a caller's condition into an index condition only when every function in
it is leakproof, which the ``jsonb`` operators ``->>``, ``->`` and ``@>`` are not (measured on
PostgreSQL 17: the partial expression indexes first written for this revision were entered by
their tenant prefix alone). So the key is written a second time as plain columns:

- one row per contract an event names: ``(tenant_id, contract_id, chain_seq, occurred_at,
  audit_event_id)``, ``PRIMARY KEY (tenant_id, contract_id, chain_seq)`` — the events of a contract
  in chain order under one b-tree prefix; ``occurred_at`` and ``audit_event_id`` are the event's
  own key, so the join reaches one partition of ``audit_event``;
- IM-A (DB-01: no UPDATE, DELETE or TRUNCATE; ``erev_app`` holds SELECT and INSERT), RLS-T, not
  partitioned; ``ck_audit_event_contract__chain_seq`` (``chain_seq >= 1``, as T-PLT-19);
- ``fk_audit_event_contract__tenant`` only. No key to ``audit_event``: it is a partitioned parent
  whose monthly partitions the schema lifecycle retires one at a time, and a key on the parent
  would make every partition a dependent object of the constraint (the 0040 and 0064 precedent).
  No key to ``contract``: the row repeats what the event states, and the event is the evidence.

``erev_api.audit.chain.append_events`` writes the rows in the event's transaction; nothing is
back-filled (D-99). ``audit_event`` gets no column and no index, so the partition lock footprint of
05 §2.7 is unchanged. No enum, function or trigger function is added (IM-A attaches the existing
``tg_forbid_mutation``), so the erev function count is unchanged. The downgrade drops the table.

Revision 0101 on 0102: main's head at the supervisor's merge of the lane, after 0098 at the
lane's merge of main b4e293c5 and 0085 at its merge of ada3f6f0 (supervisor ruling R-68 (e): a
revision keeps its number and follows main's head). A revision imports nothing of ``erev_api``
beyond the DDL helpers (DG-MIG-12).
"""

from __future__ import annotations

from typing import Final

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0101"
down_revision = "0102"
branch_labels = None
depends_on = None

TABLE: Final = "audit_event_contract"


def upgrade() -> None:
    """Create T-PLT-48 through the §6.5 helpers."""
    ops.create_tenant_table(
        TABLE,
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("chain_seq", sa.BigInteger(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("audit_event_id", sa.Uuid(), nullable=False),
        include_id=False,
        primary_key=["tenant_id", "contract_id", "chain_seq"],
        checks=[(f"ck_{TABLE}__chain_seq", "chain_seq >= 1")],
    )
    ops.apply_class(TABLE, "IM-A")
    ops.enable_rls(TABLE, "RLS-T")


def downgrade() -> None:
    """Remove exactly what ``upgrade`` created (DG-MIG-04)."""
    ops.drop_tenant_table(TABLE)
