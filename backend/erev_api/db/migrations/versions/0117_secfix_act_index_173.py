"""Lane SECFIX-ACT, Alembic revision 0117 of register index 173 (the supervisor's rulings of
2026-10-01 on the lane's pre-build line; item EST-ONE-OPEN-VERSION-1; 04 rev 1.241 T-CON-13; PRD
rev 1.168 SM-04, ERR-93): at most one version of an estimated element is open.

``ux_estimate_version__open (tenant_id, estimate_id) WHERE status IN ('DRAFT', 'SUBMITTED')`` —
unique, so an element holds one version that is being prepared or waits for its approval. The
commands refuse a second one by name under the contract's locks (``estimates._refuse_open``); the
index holds the same for a writer below them — an import, a seed — which is the second writer an
index is for. REJECTED and WITHDRAWN are not open: such a version is revised, or stays as history
beside a new one; APPROVED, SUPERSEDED and VOIDED versions are not counted either.

The key is the tenant and the element, both ``uuid``: a row-level-security policy lets both bound
a scan (04 NC-20). The predicate compares the status with constants of E-12 ``config_status``, as
``ux_sod_rule__published`` and ``ux_policy_override__active`` do; ``remove_enum_value`` carries
such an index across the swap of the type (dev-guide DG-MIG-06).

The upgrade FAILS while an element holds two open versions — a unique index is not built over
them: one of the two is discarded, withdrawn or decided first. No table, column, type, function
or grant is added. The downgrade drops the index (DG-MIG-04). The module imports
``migration_ops`` only (DG-MIG-12).

Revision 0117, assigned by the supervisor (04 §18 rule 9). ``down_revision`` is the head of main
at the commit the lane's patch was made against (0114 at 3cecdb44, 0104 at afb04675); the
supervisor re-points it at the join if main's head has moved again (ruling R-68 (e)).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0117"
down_revision = "0104"
branch_labels = None
depends_on = None

VERSION: Final = "estimate_version"
OPEN_INDEX: Final = "ux_estimate_version__open"
# The two statuses in which a version is being prepared or waits for its approval (E-12).
OPEN_PREDICATE: Final = "status IN ('DRAFT', 'SUBMITTED')"


def upgrade() -> None:
    ops.create_indexes(
        VERSION, [(OPEN_INDEX, ["tenant_id", "estimate_id"], OPEN_PREDICATE)], unique=True
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created (DG-MIG-04)."""
    ops.execute(f"DROP INDEX erev.{OPEN_INDEX}")
