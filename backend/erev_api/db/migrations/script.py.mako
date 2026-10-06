"""BUILD_SPEC item ${item}: ${message}.

04 ids created: name the T-, E- and DB- ids this revision creates (DG-MIG-02).
"""

from __future__ import annotations

from erev_api.db import migration_ops as ops

revision = "${number}"
down_revision = ${repr(down_revision)}
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.execute("SELECT 1")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.execute("SELECT 1")
