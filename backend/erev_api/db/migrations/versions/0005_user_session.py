"""BUILD_SPEC item PLF-2: passwords, sessions, CSRF and login throttling.

04 ids created: E-104 ``session_end_reason``; T-PLT-08 ``user_session`` (IM-E, RLS-NONE-U; §14.2
grants ``SELECT, INSERT, UPDATE, DELETE`` to ``erev_app``). The foreign key
``operator_support_grant_id`` → ``support_grant`` belongs to the revision that creates T-PLT-33
(DG-MIG-03).

The enum labels are pinned as literals at this revision's authoring state (DG-MIG-12; D-98
candidate 108): a revision never reads the live Python enum.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# E-104 at this revision (DG-MIG-12 literals).
SESSION_END_REASON: tuple[str, ...] = (
    "LOGOUT",
    "IDLE_TIMEOUT",
    "ABSOLUTE_TIMEOUT",
    "REVOKED",
    "PASSWORD_CHANGED",
)


def _timestamp(name: str, *, nullable: bool = True, now_default: bool = False) -> sa.Column[Any]:
    default = sa.text("now()") if now_default else None
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable, server_default=default)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("session_end_reason", SESSION_END_REASON)
    ops.create_global_table(
        "user_session",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_sha256", ops.NamedType("erev.sha256"), nullable=False),
        sa.Column("csrf_token_sha256", ops.NamedType("erev.sha256"), nullable=False),
        sa.Column("auth_method", ops.NamedType("erev.identity_provider_kind"), nullable=False),
        _timestamp("mfa_verified_at"),
        sa.Column("active_tenant_id", sa.Uuid(), nullable=True),
        _timestamp("created_at", nullable=False, now_default=True),
        _timestamp("last_seen_at", nullable=False, now_default=True),
        _timestamp("idle_expires_at", nullable=False),
        _timestamp("absolute_expires_at", nullable=False),
        _timestamp("ended_at"),
        sa.Column("end_reason", ops.NamedType("erev.session_end_reason"), nullable=True),
        sa.Column("operator_support_grant_id", sa.Uuid(), nullable=True),
        sa.Column("ip_address", ops.NamedType("inet"), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        _timestamp("expires_at"),
        primary_key=["id"],
        checks=[("ck_user_session__end_reason", "(ended_at IS NULL) = (end_reason IS NULL)")],
        unique=[("ux_user_session__token", ["token_sha256"], None)],
        indexes=[("ix_user_session__user", ["user_id", "ended_at"], None)],
    )
    ops.add_global_fk("user_session", "user_id", "app_user")
    ops.add_global_fk("user_session", "active_tenant_id", "tenant")
    ops.apply_class("user_session", "IM-E")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_global_table("user_session")
    ops.drop_enum("session_end_reason")
