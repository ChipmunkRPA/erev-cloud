"""PLF-31 (proposed; lane P2): security_event key attribution, 04 T-PLT-06 rev 1.12 (SPEC-Q-116).

04 ids amended: T-PLT-06 ``security_event`` gains ``hmac_key_id`` (text, NULL on the rows written
before this revision, which are attributed to ``security-hmac:1``) and ``canonical_version``
(smallint, default 1, the form of the HMAC preimage; new rows are written with 2, whose preimage
includes both columns), with ``ck_security_event__canonical_version`` and
``ck_security_event__key_attribution``. Existing rows keep their hash and their preimage (form 1);
nothing is rewritten or backfilled (DG-KRN-AUD-08). The IM-A triggers of 0004 already forbid UPDATE
and DELETE, so the new columns are immutable with the row, and the table-level SELECT and INSERT
grants of the class cover them; no function or trigger is added.
"""

from __future__ import annotations

from erev_api.db import migration_ops as ops

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None

TABLE = "erev.security_event"


def upgrade() -> None:
    ops.execute(
        f"ALTER TABLE {TABLE} "
        "ADD COLUMN hmac_key_id text NULL, "
        "ADD COLUMN canonical_version smallint NOT NULL DEFAULT 1"
    )
    ops.execute(
        f"ALTER TABLE {TABLE} ADD CONSTRAINT ck_security_event__canonical_version "
        "CHECK (canonical_version IN (1, 2))"
    )
    # A row without a key id is a form-1 row and the reverse (04 T-PLT-06 rev 1.12).
    ops.execute(
        f"ALTER TABLE {TABLE} ADD CONSTRAINT ck_security_event__key_attribution "
        "CHECK ((canonical_version = 1) = (hmac_key_id IS NULL))"
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT ck_security_event__key_attribution")
    ops.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT ck_security_event__canonical_version")
    ops.execute(f"ALTER TABLE {TABLE} DROP COLUMN canonical_version")
    ops.execute(f"ALTER TABLE {TABLE} DROP COLUMN hmac_key_id")
