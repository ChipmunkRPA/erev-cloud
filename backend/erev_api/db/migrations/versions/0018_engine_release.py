"""BUILD_SPEC item PLF-20: engine release stamping and explain service core.

04 ids created: T-PLT-38 ``engine_release`` (IM-A, RLS-NONE-G, PT-N; §14.2 grants ``SELECT, INSERT``
to ``erev_app``) with ``ux_engine_release__version (engine_version, build_sha)``; its DB-01 triggers
``tg_engine_release__immutable`` and ``tg_engine_release__truncate``.
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_global_table(
        "engine_release",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("engine_version", sa.Text(), nullable=False),
        sa.Column("build_sha", sa.Text(), nullable=False),
        sa.Column("schema_revision", sa.Text(), nullable=False),
        sa.Column(
            "deployed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("release_notes", ops.NamedType("erev.memo"), nullable=True),
        sa.Column(
            "control_impact_tags",
            sa.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "gate_results", ops.NamedType("jsonb"), nullable=False, server_default=sa.text("'{}'")
        ),
        primary_key=["id"],
        unique=[("ux_engine_release__version", ["engine_version", "build_sha"], None)],
    )
    # Not a global_reference table: erev_app also inserts the release of a starting process.
    ops.apply_class("engine_release", "IM-A")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_global_table("engine_release")
