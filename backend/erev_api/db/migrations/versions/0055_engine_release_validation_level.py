"""BUILD_SPEC item SOP-3 (D-96 (3); 05 REL-06; 04 rev 1.29): T-PLT-38 ``engine_release`` gains
``validation_level``, and the six enum types of 04 §3.4 E-125 to E-130 are created.

Revision number assigned at slice 1c (2026-09-19, supervisor): **0055** on ``down_revision`` "0054"
— P5 is the first migration-bearing lane to merge; P2, C1b, F-ADM, P4, F-LMG and F-SNP re-parent at
their turns. Drafted as the provisional 0097 in slices 1 and 1b; not applied to any database until
the merge and the Ray-side migration of the dev database (DG-MIG-02, DG-MIG-08).


04 ids amended: T-PLT-38 column ``validation_level`` text NOT NULL DEFAULT 'PATCH' with the check
``ck_engine_release__validation_level`` (NC-16) — the author's REL-01 declaration persisted at
REL-03 stamping. 04 ids created (slice 1b; Codex 0515; 04 §18 rule 9): the enum types E-125
``verification_outcome``, E-126 ``release_validation_status``, E-127 ``validation_attempt_status``,
E-128 ``posting_attribution_cause``, E-129 ``validation_group_orchestration_state`` and E-130
``upgrade_processing_state`` with the §3.4 labels, ahead of the T-PLT-43 to 46, T-CON-26 and
T-SL-11 tables that use them (DG-MIG-06), so DG-ARC-09's mirror check holds in both directions. No
table, trigger, policy or grant changes: the table's §14.2 grants (``erev_app`` SELECT, INSERT)
cover the new column, and the IM-A triggers are unchanged.
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None

TABLE = "erev.engine_release"
COLUMN = "validation_level"
CHECK = "ck_engine_release__validation_level"
# 04 §3.4 E-125 to E-130, labels verbatim (tests/architecture pins them to erev_api.enums and 04).
ENUM_TYPES: Final[dict[str, tuple[str, ...]]] = {
    "verification_outcome": (
        "MATCH",
        "MISMATCH",
        "DIFFERENCES",
        "UNVERIFIABLE",
        "NO_SOURCE",
        "ERROR",
    ),
    "release_validation_status": (
        "PENDING",
        "RUNNING",
        "INCOMPLETE",
        "PASSED",
        "FAILED",
        "PENDING_APPROVAL",
        "APPROVED",
        "REJECTED",
    ),
    "validation_attempt_status": ("SELECTED", "RUNNING", "COMPLETE", "INCOMPLETE", "SUPERSEDED"),
    "posting_attribution_cause": ("UPGRADE_CONTEXT", "UPGRADE_ONLY", "UPGRADE_AND_OTHER_INPUTS"),
    "validation_group_orchestration_state": (
        "PENDING",
        "RUNNING",
        "RETRYABLE",
        "COMPLETE",
        "FAILED_EXHAUSTED",
        "CANCELLED",
    ),
    "upgrade_processing_state": (
        "PENDING",
        "DEFERRED_NO_OPEN_PERIOD",
        "SETTLED_NO_POSTING",
        "POSTED",
    ),
}


def upgrade() -> None:
    """Add the column with its default and named check, then the six enum types (04 §18 rule 9: an
    ALTER of the step-0002 table and the types the rule-8 tables will use; no new table)."""
    ops.execute(f"ALTER TABLE {TABLE} ADD COLUMN {COLUMN} text NOT NULL DEFAULT 'PATCH'")
    ops.execute(
        f"ALTER TABLE {TABLE} ADD CONSTRAINT {CHECK} CHECK ({COLUMN} IN ('PATCH','MINOR','MAJOR'))"
    )
    for name, labels in ENUM_TYPES.items():
        ops.create_enum(name, labels)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    for name in reversed(ENUM_TYPES):
        ops.drop_enum(name)
    ops.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT {CHECK}")
    ops.execute(f"ALTER TABLE {TABLE} DROP COLUMN {COLUMN}")
