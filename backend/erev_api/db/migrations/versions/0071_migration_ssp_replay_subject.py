"""D-98 candidate 133 AMENDMENT 4 (lane F-LMG; 04 rev 1.72): E-08 ``approval_subject_type`` gains
``MIGRATION_SSP_REPLAY`` — the mode-(a) legacy SSP replay request submitted at ``POST
/migrations/{id}/import``
and auto-approved under ``AUTO-MIG-01`` (02-PRD §2.5 rev 1.15), the approval basis EREV-CFG-002
requires for the
replayed ``LEGACY-SKU-SSP`` versions.

Revision 0071 on 0070, assigned by the team-lead (04 §18 rule 9; sequence F-CTR 0068 → F-CTR 0069 →
F-CTR 0070 (the GUARD-TRN-1
re-render fix) → F-LMG 0071; F-ADM's 0072 follows). Enum value only; no table, column, function or
trigger changes. The downgrade rewrites the
type without the label through ``remove_enum_value`` (DG-MIG-06), which fails while a row still
carries it.
"""

from __future__ import annotations

from erev_api.db import migration_ops as ops

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None

ENUM = "approval_subject_type"
VALUE = "MIGRATION_SSP_REPLAY"


def upgrade() -> None:
    ops.add_enum_value(ENUM, VALUE)


def downgrade() -> None:
    ops.remove_enum_value(ENUM, VALUE)
