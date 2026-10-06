"""BUILD_SPEC item PLF-1: identity and tenant directory.

04 ids created: E-15 ``principal_kind``, E-16 ``tenant_kind``, E-78 ``membership_status``, E-79
``security_event_kind``, E-80 ``identity_provider_kind``, E-81 ``audit_outcome``, E-101
``tenant_status`` and E-102 ``user_status``; T-PLT-03 ``identity_provider`` and T-PLT-02
``app_user`` (IM-M, RLS-NONE-U, DB-13 column grants); T-PLT-01 ``tenant`` (IM-M, RLS-TN with the
DB-15 INSERT policy ``pl_tenant__provisioning``); T-PLT-07 ``tenant_membership`` (IM-M, RLS-TM);
T-PLT-06 ``security_event`` (IM-A, RLS-NONE-U); DB-02 touch triggers; DB-05 ``tg_tenant__frozen``
(``kind``, ``source_tenant_id``); DB-01 triggers on ``security_event``; §14.2 grants.

The enum labels are pinned as literals at this revision's authoring state (DG-MIG-12; D-98
candidate 108): a revision never reads the live Python enum. ``security_event_kind`` therefore
ends at ``PASSWORD_RESET_COMPLETED``; revision 0058 adds ``INVITATION_LOOKUP_FAILED``.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# E-15, E-16, E-78, E-79, E-80, E-81, E-101 and E-102 at this revision (DG-MIG-12 literals).
ENUMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("principal_kind", ("USER", "API_CLIENT", "SYSTEM", "OPERATOR")),
    ("tenant_kind", ("production", "sandbox")),
    ("membership_status", ("INVITED", "ACTIVE", "SUSPENDED", "REMOVED")),
    (
        "security_event_kind",
        (
            "LOGIN_SUCCEEDED",
            "LOGIN_FAILED",
            "LOGOUT",
            "ACCOUNT_LOCKED",
            "PASSWORD_CHANGED",
            "MFA_ENROLLED",
            "MFA_RESET",
            "MFA_CHALLENGE_FAILED",
            "RECOVERY_CODE_USED",
            "SESSION_EXPIRED",
            "TENANT_SELECTED",
            "OIDC_LINKED",
            "PLATFORM_SCOPE_USED",
            "PASSWORD_RESET_REQUESTED",
            "PASSWORD_RESET_COMPLETED",
        ),
    ),
    ("identity_provider_kind", ("password", "oidc", "saml")),
    ("audit_outcome", ("SUCCESS", "DENIED", "FAILED")),
    ("tenant_status", ("ACTIVE", "SUSPENDED", "ARCHIVED")),
    ("user_status", ("ACTIVE", "LOCKED", "DISABLED")),
)
# 04 §14.2: the app_user columns erev_app may update.
APP_USER_UPDATE_COLUMNS = (
    "display_name",
    "password_hash",
    "password_changed_at",
    "status",
    "failed_login_count",
    "locked_until",
    "identity_provider_id",
    "last_login_at",
    "preferences",
    "updated_at",
    "updated_by",
    "updated_by_kind",
    "row_version",
)
# DB-05: tenant.kind and tenant.source_tenant_id never change after insert.
TENANT_FROZEN_BODY = """
BEGIN
  IF NEW.kind IS DISTINCT FROM OLD.kind
     OR NEW.source_tenant_id IS DISTINCT FROM OLD.source_tenant_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-001: kind and source_tenant_id of %s cannot change', OLD.id);
  END IF;
  RETURN NEW;
END
"""


def _type(name: str) -> ops.NamedType:
    return ops.NamedType(name)


def _timestamp(name: str, *, nullable: bool = True, now_default: bool = False) -> sa.Column[Any]:
    default = sa.text("now()") if now_default else None
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable, server_default=default)


def _empty_object(name: str) -> sa.Column[Any]:
    return sa.Column(name, _type("jsonb"), nullable=False, server_default=sa.text("'{}'::jsonb"))


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    for name, values in ENUMS:
        ops.create_enum(name, values)

    ops.create_global_table(
        "identity_provider",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", _type("erev.code"), nullable=False),
        sa.Column("kind", _type("erev.identity_provider_kind"), nullable=False),
        sa.Column("display_name", _type("erev.label"), nullable=False),
        sa.Column("issuer_url", sa.Text(), nullable=True),
        sa.Column("client_id", sa.Text(), nullable=True),
        sa.Column("client_secret_ref", sa.Text(), nullable=True),
        _empty_object("config"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        primary_key=["id"],
        standard_sets=["SC-C", "SC-M"],
        checks=[("ck_identity_provider__config", "jsonb_typeof(config) = 'object'")],
        unique=[("ux_identity_provider__code", ["code"], None)],
    )
    ops.apply_class("identity_provider", "IM-M", select_only=True)

    ops.create_global_table(
        "app_user",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", _type("erev.email"), nullable=False),
        sa.Column("display_name", _type("erev.label"), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        _timestamp("password_changed_at"),
        sa.Column(
            "status", _type("erev.user_status"), nullable=False, server_default=sa.text("'ACTIVE'")
        ),
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        _timestamp("locked_until"),
        sa.Column("identity_provider_id", sa.Uuid(), nullable=True),
        sa.Column("external_id", sa.Text(), nullable=True),
        sa.Column("is_operator", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        _empty_object("preferences"),
        _timestamp("last_login_at"),
        primary_key=["id"],
        standard_sets=["SC-C", "SC-M"],
        checks=[
            ("ck_app_user__failed_login_count", "failed_login_count >= 0"),
            ("ck_app_user__preferences", "jsonb_typeof(preferences) = 'object'"),
        ],
        unique=[
            ("ux_app_user__email", ["email"], None),
            (
                "ux_app_user__idp_external",
                ["identity_provider_id", "external_id"],
                "external_id IS NOT NULL",
            ),
        ],
    )
    ops.add_global_fk("app_user", "identity_provider_id", "identity_provider")
    ops.apply_class("app_user", "IM-M", update_columns=APP_USER_UPDATE_COLUMNS)

    ops.create_global_table(
        "tenant",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", _type("erev.code"), nullable=False),
        sa.Column("kind", _type("erev.tenant_kind"), nullable=False),
        sa.Column(
            "status",
            _type("erev.tenant_status"),
            nullable=False,
            server_default=sa.text("'ACTIVE'"),
        ),
        sa.Column("display_name", _type("erev.label"), nullable=False),
        sa.Column("reporting_currency", _type("erev.currency_code"), nullable=False),
        sa.Column("source_tenant_id", sa.Uuid(), nullable=True),
        _timestamp("source_known_at"),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("industry_cluster", sa.Text(), nullable=True),
        sa.Column("audit_hmac_key_id", sa.Text(), nullable=False),
        sa.Column("default_locale", sa.Text(), nullable=False, server_default=sa.text("'en-US'")),
        _timestamp("setup_completed_at"),
        _timestamp("ai_disabled_at"),
        sa.Column("ai_disabled_by", sa.Uuid(), nullable=True),
        sa.Column("ai_disabled_by_kind", _type("erev.principal_kind"), nullable=True),
        primary_key=["id"],
        standard_sets=["SC-C", "SC-M"],
        checks=[
            ("ck_tenant__source_tenant", "kind = 'sandbox' OR source_tenant_id IS NULL"),
            ("ck_tenant__ai_disabled", "(ai_disabled_at IS NULL) = (ai_disabled_by_kind IS NULL)"),
        ],
        unique=[("ux_tenant__code", ["code"], None)],
        indexes=[("ix_tenant__source_tenant_id", ["source_tenant_id"], None)],
    )
    ops.add_global_fk("tenant", "reporting_currency", "currency", target_column="code")
    ops.add_global_fk("tenant", "source_tenant_id", "tenant")
    ops.apply_class("tenant", "IM-M")
    ops.create_trigger(
        "tenant",
        "frozen",
        TENANT_FROZEN_BODY,
        timing="BEFORE",
        events="UPDATE OF kind, source_tenant_id",
    )

    ops.create_tenant_table(
        "tenant_membership",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            _type("erev.membership_status"),
            nullable=False,
            server_default=sa.text("'INVITED'"),
        ),
        _timestamp("invited_at", nullable=False, now_default=True),
        sa.Column("invitation_token_sha256", _type("erev.sha256"), nullable=True),
        _timestamp("invitation_expires_at"),
        _timestamp("activated_at"),
        _timestamp("removed_at"),
        _timestamp("last_opened_at"),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            (
                "ck_tenant_membership__invitation_token",
                "(status = 'INVITED') = (invitation_token_sha256 IS NOT NULL)",
            ),
            (
                "ck_tenant_membership__invitation_expiry",
                "(invitation_token_sha256 IS NULL) = (invitation_expires_at IS NULL)",
            ),
        ],
        unique=[("ux_tenant_membership__user", ["tenant_id", "user_id"], None)],
    )
    # Cross-tenant lookups that 04 T-PLT-07 specifies: the RLS-TN subquery and invitation lookup.
    ops.create_indexes(
        "tenant_membership",
        [("ix_tenant_membership__user_id", ["user_id"], None)],
        unique=False,
        tenant_leading=False,
    )
    ops.create_indexes(
        "tenant_membership",
        [
            (
                "ux_tenant_membership__invitation",
                ["invitation_token_sha256"],
                "invitation_token_sha256 IS NOT NULL",
            )
        ],
        unique=True,
        tenant_leading=False,
    )
    ops.add_global_fk("tenant_membership", "user_id", "app_user")
    ops.apply_class("tenant_membership", "IM-M")
    # RLS-TN reads tenant_membership, so both tables exist before the policies.
    ops.enable_rls("tenant", "RLS-TN")
    ops.enable_rls("tenant_membership", "RLS-TM")

    ops.create_global_table(
        "security_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chain_seq", sa.BigInteger(), nullable=False),
        _timestamp("occurred_at", nullable=False, now_default=True),
        sa.Column("kind", _type("erev.security_event_kind"), nullable=False),
        sa.Column("outcome", _type("erev.audit_outcome"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("email_sha256", _type("erev.sha256"), nullable=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("ip_address", _type("inet"), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=False),
        _empty_object("detail"),
        sa.Column("prev_hmac", _type("erev.sha256"), nullable=True),
        sa.Column("hmac", _type("erev.sha256"), nullable=False),
        primary_key=["id"],
        checks=[("ck_security_event__detail", "jsonb_typeof(detail) = 'object'")],
        unique=[("ux_security_event__chain_seq", ["chain_seq"], None)],
        indexes=[("ix_security_event__user_occurred", ["user_id", "occurred_at"], None)],
    )
    ops.add_global_fk("security_event", "user_id", "app_user")
    ops.add_global_fk("security_event", "tenant_id", "tenant")
    ops.apply_class("security_event", "IM-A")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_global_table("security_event")
    # The RLS-TN SELECT policy depends on tenant_membership.
    ops.execute("DROP POLICY pl_tenant__select ON erev.tenant")
    ops.drop_tenant_table("tenant_membership")
    ops.drop_tenant_table("tenant")
    ops.drop_global_table("app_user")
    ops.drop_global_table("identity_provider")
    for name, _ in reversed(ENUMS):
        ops.drop_enum(name)
