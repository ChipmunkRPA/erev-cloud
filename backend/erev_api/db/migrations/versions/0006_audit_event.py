"""BUILD_SPEC item PLF-3: audit log and hash chain.

04 ids created: T-PLT-22 ``audit_chain_head`` (IM-X, RLS-T); T-PLT-19 ``audit_event`` (IM-A, RLS-T,
PT-MOC with the monthly partitions 2018-01 to 2032-12 and ``audit_event_pdefault``); DB-01 triggers
on ``audit_event`` and its partitions; DB-09 ``tg_audit_event__chain``. The foreign keys
``approval_request_id``, ``api_client_id`` and ``support_grant_id`` belong to the revisions that
create their targets (DG-MIG-03).
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# DB-09: the head row lock serialises appends; a row of another tenant is left to RLS (42501).
AUDIT_CHAIN_BODY = """
DECLARE
  head_seq bigint;
  head_hmac erev.sha256;
BEGIN
  SELECT h.last_chain_seq, h.last_hmac INTO head_seq, head_hmac
    FROM erev.audit_chain_head h
   WHERE h.tenant_id = NEW.tenant_id
     FOR UPDATE;
  IF NOT FOUND THEN
    IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id() THEN
      RETURN NEW;
    END IF;
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-AUD-001: tenant %s has no audit chain head', NEW.tenant_id);
  END IF;
  IF NEW.chain_seq IS DISTINCT FROM head_seq + 1 OR NEW.prev_hmac IS DISTINCT FROM head_hmac THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-AUD-001: audit event %s does not continue the chain of tenant %s '
                       'at chain_seq %s', NEW.id, NEW.tenant_id, head_seq + 1);
  END IF;
  UPDATE erev.audit_chain_head
     SET last_chain_seq = NEW.chain_seq,
         last_hmac = NEW.hmac,
         last_occurred_at = NEW.occurred_at,
         updated_at = now()
   WHERE tenant_id = NEW.tenant_id;
  RETURN NEW;
END
"""


def _timestamp(name: str, *, nullable: bool = True, now_default: bool = False) -> sa.Column[Any]:
    default = sa.text("now()") if now_default else None
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable, server_default=default)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_tenant_table(
        "audit_chain_head",
        sa.Column("last_chain_seq", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_hmac", ops.NamedType("erev.sha256"), nullable=True),
        _timestamp("last_occurred_at"),
        _timestamp("updated_at", nullable=False, now_default=True),
        include_id=False,
        primary_key=["tenant_id"],
        checks=[
            ("ck_audit_chain_head__last_chain_seq", "last_chain_seq >= 0"),
            ("ck_audit_chain_head__last_hmac", "(last_chain_seq = 0) = (last_hmac IS NULL)"),
        ],
    )
    ops.apply_class("audit_chain_head", "IM-X")
    ops.enable_rls("audit_chain_head", "RLS-T")

    ops.create_tenant_table(
        "audit_event",
        _timestamp("occurred_at", nullable=False, now_default=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chain_seq", sa.BigInteger(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_kind", ops.NamedType("erev.principal_kind"), nullable=False),
        sa.Column(
            "actor_roles",
            ops.NamedType("text[]"),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
        sa.Column("auth_method", sa.Text(), nullable=True),
        sa.Column("mfa_verified", sa.Boolean(), nullable=True),
        sa.Column("on_behalf_of_id", sa.Uuid(), nullable=True),
        sa.Column("api_client_id", sa.Uuid(), nullable=True),
        sa.Column("support_grant_id", sa.Uuid(), nullable=True),
        sa.Column("source_ip", ops.NamedType("inet"), nullable=True),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("object_type", sa.Text(), nullable=False),
        sa.Column("object_id", sa.Uuid(), nullable=True),
        sa.Column("object_version", sa.Text(), nullable=True),
        sa.Column("before", ops.NamedType("jsonb"), nullable=True),
        sa.Column("after", ops.NamedType("jsonb"), nullable=True),
        sa.Column("diff", ops.NamedType("jsonb"), nullable=True),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("comment", ops.NamedType("erev.memo"), nullable=True),
        sa.Column("approval_request_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", ops.NamedType("erev.audit_outcome"), nullable=False),
        sa.Column(
            "detail", ops.NamedType("jsonb"), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("prev_hmac", ops.NamedType("erev.sha256"), nullable=True),
        sa.Column("hmac", ops.NamedType("erev.sha256"), nullable=False),
        sa.Column("hmac_key_id", sa.Text(), nullable=False),
        include_id=False,
        partition_by="occurred_at",
        primary_key=["tenant_id", "occurred_at", "id"],
        checks=[
            ("ck_audit_event__action", "action ~ '^[a-z_]+\\.[a-z_]+$'"),
            ("ck_audit_event__chain_seq", "chain_seq >= 1"),
            ("ck_audit_event__prev_hmac", "(chain_seq = 1) = (prev_hmac IS NULL)"),
            ("ck_audit_event__diff", "diff IS NULL OR jsonb_typeof(diff) = 'array'"),
            ("ck_audit_event__detail", "jsonb_typeof(detail) = 'object'"),
        ],
        indexes=[
            ("ix_audit_event__chain", ["tenant_id", "chain_seq"], None),
            (
                "ix_audit_event__object",
                ["tenant_id", "object_type", "object_id", "occurred_at"],
                None,
            ),
            ("ix_audit_event__actor", ["tenant_id", "actor_id", "occurred_at"], None),
            ("ix_audit_event__action", ["tenant_id", "action", "occurred_at"], None),
        ],
    )
    ops.create_monthly_partitions("audit_event")
    ops.apply_class("audit_event", "IM-A")
    ops.enable_rls("audit_event", "RLS-T")
    ops.create_trigger("audit_event", "chain", AUDIT_CHAIN_BODY, timing="BEFORE", events="INSERT")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("audit_event")
    ops.drop_tenant_table("audit_chain_head")
