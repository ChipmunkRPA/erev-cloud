"""BUILD_SPEC item PLF-25: API clients, OAuth tokens and bearer authentication.

04 ids created: E-103 ``api_client_status``; T-PLT-15 ``api_client`` (IM-M, RLS-T) with
``ck_api_client__entity_ids``, ``ux_api_client__client_id`` (global: the value embeds the tenant)
and the DB-12 triggers ``tg_api_client__scopes`` (no approval permission, and only catalogue codes)
and ``tg_api_client__entity_ids`` (fail closed until ``legal_entity`` exists, BUILD_SPEC BS1-D-06);
T-PLT-16 ``api_token`` (IM-E, RLS-T) with ``ux_api_token__hash`` and the composite foreign key
``api_client_id`` to ``api_client``.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

# 04 §3.4 E-103.
API_CLIENT_STATUS = ("ACTIVE", "REVOKED")

# DB-12: scopes are catalogue permission codes and never approval permissions (CTL-037).
SCOPES_BODY = """
DECLARE
  unknown text;
  approval text;
BEGIN
  SELECT string_agg(u.code, ', ' ORDER BY u.code) INTO unknown
    FROM unnest(NEW.scopes) AS u(code)
   WHERE NOT EXISTS (SELECT 1 FROM erev.permission p WHERE p.code = u.code);
  IF unknown IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-002: permission codes %s of %I.%I do not exist',
                       unknown, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  SELECT string_agg(p.code, ', ' ORDER BY p.code) INTO approval
    FROM erev.permission p
   WHERE p.code = ANY (NEW.scopes) AND p.is_approval;
  IF approval IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-002: scopes %s of %I.%I are approval permissions',
                       approval, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""
# DB-12 fail closed (BS1-D-06): no entity id can be validated before legal_entity exists.
ENTITY_IDS_BODY = """
BEGIN
  IF cardinality(NEW.entity_ids) > 0 THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-002: entity_ids of %I.%I name no existing legal entity',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""


def _timestamp(name: str, *, nullable: bool = True, now_default: bool = False) -> sa.Column[Any]:
    default = sa.text("now()") if now_default else None
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable, server_default=default)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("api_client_status", API_CLIENT_STATUS)

    ops.create_tenant_table(
        "api_client",
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("secret_hash", sa.Text(), nullable=False),
        _timestamp("secret_rotated_at"),
        sa.Column("scopes", ops.NamedType("text[]"), nullable=False),
        sa.Column("is_all_entities", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "entity_ids",
            ops.NamedType("uuid[]"),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "status",
            ops.NamedType("erev.api_client_status"),
            nullable=False,
            server_default=sa.text("'ACTIVE'"),
        ),
        _timestamp("expires_at", nullable=False),
        sa.Column(
            "rate_limit_per_minute", sa.Integer(), nullable=False, server_default=sa.text("600")
        ),
        _timestamp("last_used_at"),
        standard_sets=["SC-C", "SC-M"],
        checks=[("ck_api_client__entity_ids", "is_all_entities = (cardinality(entity_ids) = 0)")],
    )
    # 04 T-PLT-15: unique globally, which is safe because the value embeds the tenant.
    ops.create_indexes(
        "api_client",
        [("ux_api_client__client_id", ["client_id"], None)],
        unique=True,
        tenant_leading=False,
    )
    ops.apply_class("api_client", "IM-M")
    ops.enable_rls("api_client", "RLS-T")
    ops.create_trigger(
        "api_client", "scopes", SCOPES_BODY, timing="BEFORE", events="INSERT OR UPDATE OF scopes"
    )
    ops.create_trigger(
        "api_client",
        "entity_ids",
        ENTITY_IDS_BODY,
        timing="BEFORE",
        events="INSERT OR UPDATE OF entity_ids",
    )

    ops.create_tenant_table(
        "api_token",
        sa.Column("api_client_id", sa.Uuid(), nullable=False),
        sa.Column("token_sha256", ops.NamedType("erev.sha256"), nullable=False),
        sa.Column("scopes", ops.NamedType("text[]"), nullable=False),
        _timestamp("issued_at", nullable=False, now_default=True),
        _timestamp("expires_at", nullable=False),
        _timestamp("revoked_at"),
        unique=[("ux_api_token__hash", ["tenant_id", "token_sha256"], None)],
    )
    ops.add_tenant_fk("api_token", "api_client_id", "api_client")
    ops.apply_class("api_token", "IM-E")
    ops.enable_rls("api_token", "RLS-T")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("api_token")
    ops.drop_tenant_table("api_client")
    ops.drop_enum("api_client_status")
