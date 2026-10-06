"""BUILD_SPEC item PLF-23: audit read API and chain verification job.

04 ids created: E-98 ``control_result``; T-PLT-23 ``audit_chain_verification`` (IM-A, RLS-T; §14.2
grants ``SELECT, INSERT`` to ``erev_app``) with ``ck_audit_chain_verification__trigger``,
``ix_audit_chain_verification__finished`` and the composite foreign keys ``digest_file_id`` to
``file_object`` and ``job_id`` to ``job``.
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

# 04 §3.4 E-98.
CONTROL_RESULT = ("PASS", "FAIL", "NOT_APPLICABLE")


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("control_result", CONTROL_RESULT)
    timestamp = sa.DateTime(timezone=True)
    ops.create_tenant_table(
        "audit_chain_verification",
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("from_chain_seq", sa.BigInteger(), nullable=False),
        sa.Column("to_chain_seq", sa.BigInteger(), nullable=False),
        sa.Column("events_checked", sa.BigInteger(), nullable=False),
        sa.Column("result", ops.NamedType("erev.control_result"), nullable=False),
        sa.Column("first_failure_seq", sa.BigInteger(), nullable=True),
        sa.Column("failure_detail", ops.NamedType("jsonb"), nullable=True),
        sa.Column("digest_last_hmac", ops.NamedType("erev.sha256"), nullable=True),
        sa.Column("digest_file_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", timestamp, nullable=False),
        sa.Column("finished_at", timestamp, nullable=False),
        standard_sets=["SC-C"],
        checks=[
            (
                "ck_audit_chain_verification__trigger",
                "trigger IN ('SCHEDULED', 'ON_DEMAND')",
            )
        ],
        indexes=[
            ("ix_audit_chain_verification__finished", ["tenant_id", "finished_at"], None),
        ],
    )
    ops.add_tenant_fk("audit_chain_verification", "digest_file_id", "file_object")
    ops.add_tenant_fk("audit_chain_verification", "job_id", "job")
    ops.apply_class("audit_chain_verification", "IM-A")
    ops.enable_rls("audit_chain_verification", "RLS-T")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("audit_chain_verification")
    ops.drop_enum("control_result")
