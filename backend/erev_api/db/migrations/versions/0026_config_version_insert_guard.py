"""BUILD_SPEC item WEB-3d: config version insert guard.

04 ids extended: DB-04 ``erev.tg_config_version()`` refuses an INSERT whose status is not DRAFT
unless ``app.platform_scope`` is ``provisioning`` (01-DECISIONS D-80, configuration inserts). No
table, column or enum changes.
"""

from __future__ import annotations

from erev_api.db import migration_ops as ops

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Replace the DB-04 function body with the insert guard; the IM-P triggers keep calling it."""
    ops.replace_config_version_function(ops.CONFIG_VERSION_BODY)


def downgrade() -> None:
    """Restore the body revision 0009 created (DG-MIG-04)."""
    ops.replace_config_version_function(ops.CONFIG_VERSION_BODY_0009)
