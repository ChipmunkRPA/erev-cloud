"""BUILD_SPEC item PLF-7: idempotency keys and optimistic concurrency.

04 ids created: T-PLT-28 ``idempotency_record`` (IM-E, RLS-T; §14.2 grants ``SELECT, INSERT,
UPDATE, DELETE`` to ``erev_app``) with ``ix_idempotency_record__expires``. T-PLT-28 names no foreign
key for ``response_file_id``.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def _timestamp(name: str, *, nullable: bool = True, now_default: bool = False) -> sa.Column[Any]:
    default = sa.text("now()") if now_default else None
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable, server_default=default)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_tenant_table(
        "idempotency_record",
        sa.Column("principal_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("principal_kind", ops.NamedType("erev.principal_kind"), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("request_sha256", ops.NamedType("erev.sha256"), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default=sa.text("'IN_PROGRESS'")),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_headers", ops.NamedType("jsonb"), nullable=True),
        sa.Column("response_body", ops.NamedType("jsonb"), nullable=True),
        sa.Column("response_file_id", sa.Uuid(), nullable=True),
        _timestamp("created_at", nullable=False, now_default=True),
        _timestamp("completed_at"),
        _timestamp("expires_at", nullable=False),
        include_id=False,
        primary_key=["tenant_id", "principal_id", "idempotency_key"],
        checks=[
            (
                "ck_idempotency_record__idempotency_key",
                "char_length(idempotency_key) BETWEEN 8 AND 255",
            ),
            ("ck_idempotency_record__state", "state IN ('IN_PROGRESS', 'COMPLETED')"),
        ],
        # NC-03, NC-07: tenant indexes lead with tenant_id (T-PLT-28 lists expires_at alone).
        indexes=[("ix_idempotency_record__expires", ["tenant_id", "expires_at"], None)],
    )
    ops.apply_class("idempotency_record", "IM-E")
    ops.enable_rls("idempotency_record", "RLS-T")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("idempotency_record")
