"""ENG-C6: T-SL-12 ``subledger_line_event`` (04 rev 1.48; ENGINE_SPEC_B S14-R-13a, S15-R-18b;
D-98 candidates 95 and 102b; Codex C6-RPT-R3 on record 343e0392).

Revision ``0064`` on ``0063`` (lane F-SNP's ``0063_snp_1_retention_parameter``), assigned by the
supervisor at merge prep on 2026-09-20 (04 §18 rule 11) and landed at the merge of main f84770d4
into sprint/l6 (lane record docs/reviews/loop/sprint/ENG-C6.md).

One row per (subledger line, first-included contract event) with ``ordinal`` = the event's 1-based
position in ENG-06 order: the lineage of a cumulative posting delta, which carries no single
``contract_event_id`` (L2-5-Q-36). The out-of-period register attributes such lines to this set
exactly once (conservation) and refuses a line with neither attribution by name (S15-R-18b).

- IM-A (04 §1.5; DB-01), RLS-T; SC-C stamped like the posting's lines; no ``id`` — the key is
  ``(tenant_id, subledger_line_id, contract_event_id)`` (04 T-SL-12).
- ``ck_subledger_line_event__ordinal`` (``ordinal >= 1``); ``ux_subledger_line_event__ordinal``
  (one position per line); ``ix_subledger_line_event__event`` (reverse lookup by event).
- Foreign key (rule 2): ``fk_subledger_line_event__contract_event`` only. The pair
  ``(subledger_line_period_end_date, subledger_line_id)`` names a T-SL-04 row without a key:
  ``subledger_line`` is a partitioned parent whose monthly partitions the schema lifecycle
  retires one at a time (L3-1-Q-24), and a key on the parent would make every partition a
  dependent object of the constraint — the reason 0040 left ``schedule_line_id`` and
  ``reverses_line_id`` without one (L3-1-Q-28).

No enum, function or existing-table change.
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None

TABLE = "subledger_line_event"


def upgrade() -> None:
    """Create T-SL-12 through the §6.5 helpers (04 §18 step 0006, rule 11)."""
    ops.create_tenant_table(
        TABLE,
        sa.Column("subledger_line_id", sa.Uuid(), nullable=False),
        sa.Column("subledger_line_period_end_date", sa.Date(), nullable=False),
        sa.Column("contract_event_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        standard_sets=["SC-C"],
        include_id=False,
        primary_key=["tenant_id", "subledger_line_id", "contract_event_id"],
        checks=[(f"ck_{TABLE}__ordinal", "ordinal >= 1")],
        unique=[(f"ux_{TABLE}__ordinal", ["tenant_id", "subledger_line_id", "ordinal"], None)],
        indexes=[(f"ix_{TABLE}__event", ["tenant_id", "contract_event_id"], None)],
    )
    # No key to the partitioned subledger_line (L3-1-Q-24, L3-1-Q-28; the 0040 precedent).
    ops.add_tenant_fk(TABLE, "contract_event_id", "contract_event")
    ops.apply_class(TABLE, "IM-A")
    ops.enable_rls(TABLE, "RLS-T")


def downgrade() -> None:
    """Remove exactly what ``upgrade`` created (DG-MIG-04)."""
    ops.drop_tenant_table(TABLE)
