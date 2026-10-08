"""Retain immutable evidence-pack source bindings; never infer sources for legacy rows."""

from erev_api.db import migration_ops as ops

revision = "0142"
down_revision = "0141"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # DB-03 compares every changed column against its explicit mutable-column list.
    # This new column is deliberately not on that list and receives no UPDATE grant.
    ops.execute("ALTER TABLE erev.evidence_pack ADD COLUMN source_binding jsonb NULL")
    ops.execute(
        "ALTER TABLE erev.evidence_pack ADD CONSTRAINT ck_evidence_pack__source_binding "
        "CHECK (source_binding IS NULL OR jsonb_typeof(source_binding) = 'object')"
    )


def downgrade() -> None:
    # Constraint validation scans all rows even under FORCE ROW LEVEL SECURITY. A
    # SELECT without a tenant context could miss retained bindings of other tenants.
    ops.execute(
        "ALTER TABLE erev.evidence_pack ADD CONSTRAINT ck_evidence_pack__downgrade_unbound "
        "CHECK (source_binding IS NULL)"
    )
    ops.execute("ALTER TABLE erev.evidence_pack DROP CONSTRAINT ck_evidence_pack__source_binding")
    ops.execute("ALTER TABLE erev.evidence_pack DROP COLUMN source_binding")
