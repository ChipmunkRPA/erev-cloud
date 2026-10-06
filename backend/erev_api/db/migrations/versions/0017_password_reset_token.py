"""BUILD_SPEC item PLF-15: invitation acceptance, password reset and password change.

04 ids created: T-PLT-42 ``password_reset_token`` (IM-E, RLS-NONE-U; §14.2 grants ``SELECT, INSERT,
UPDATE (used_at, superseded_at), DELETE`` to ``erev_app``) with ``ux_password_reset_token__token``
and ``ix_password_reset_token__user``. E-79 ``PASSWORD_RESET_REQUESTED`` and
``PASSWORD_RESET_COMPLETED`` already exist (revision 0004, rev 1.2 values; DG-MIG-06).
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

# 04 §14.2: the columns erev_app may update.
PASSWORD_RESET_TOKEN_UPDATE_COLUMNS = ("used_at", "superseded_at")


def _timestamp(name: str, *, nullable: bool = True, now_default: bool = False) -> sa.Column[Any]:
    default = sa.text("now()") if now_default else None
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable, server_default=default)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_global_table(
        "password_reset_token",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_sha256", ops.NamedType("erev.sha256"), nullable=False),
        _timestamp("created_at", nullable=False, now_default=True),
        _timestamp("token_expires_at", nullable=False),
        _timestamp("used_at"),
        _timestamp("superseded_at"),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("ip_address", ops.NamedType("inet"), nullable=True),
        _timestamp("expires_at", nullable=False),
        primary_key=["id"],
        unique=[("ux_password_reset_token__token", ["token_sha256"], None)],
        indexes=[("ix_password_reset_token__user", ["user_id", "created_at"], None)],
    )
    ops.add_global_fk("password_reset_token", "user_id", "app_user")
    ops.apply_class(
        "password_reset_token", "IM-E", update_columns=PASSWORD_RESET_TOKEN_UPDATE_COLUMNS
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_global_table("password_reset_token")
