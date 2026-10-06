"""Lane SECFIX-IMP, supervisor rulings R-98 (the gap "an API client's upload is held to the
narrower of the client's stored scopes and the token's") and R-109 (a); 04 rev 1.147 T-IMP-02; 05
rev 1.86 IPL-05: ``import_upload.uploader_scopes`` — the permission codes the access token of an
API client carried when it created the upload. NULL for a person's upload.

A token's scopes are known only while the request that creates the upload runs: the principal
keeps no token reference, ``api_token`` rows are swept seven days after expiry, and the validation,
the dry run and the commit are jobs. The column keeps them, so that the upload's bounds at every
stage are the client's grants in force NOW narrowed to what the creating token carried
(``domain/imports/scope._uploader_grants``) — a grant the client gains after the upload does not
widen it.

The column is written at INSERT and never again: it is outside the updatable column list of the
DB-03 function ``tg_import_upload__transition()`` (``erev_api.db.transitions``), which refuses a
change to any column it does not name, and the app role holds no column UPDATE grant on it. So no
function is replaced, no grant is added and the installed function source stays the fresh
rendering (DG-ARC-07). The downgrade drops the column; no row is rewritten.

Revision number 0102 assigned by the supervisor (ruling R-109 (a)). It is built on ``0087``, the
head of the lane's tree, which cannot take main; the supervisor re-points ``down_revision`` to
main's head at the merge (ruling R-68 (e) — never two heads on main).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0102"
down_revision = "0098"
branch_labels = None
depends_on = None

TABLE: Final = "import_upload"
COLUMN: Final = "uploader_scopes"


def upgrade() -> None:
    ops.execute(f"ALTER TABLE erev.{TABLE} ADD COLUMN {COLUMN} text[] NULL")


def downgrade() -> None:
    """Remove exactly what upgrade() created (DG-MIG-04)."""
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP COLUMN {COLUMN}")
