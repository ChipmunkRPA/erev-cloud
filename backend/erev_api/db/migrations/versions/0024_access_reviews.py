"""BUILD_SPEC item PLF-28: access review campaigns.

04 ids created: E-107 ``access_review_status``; E-108 ``access_review_decision``; T-PLT-40
``access_review_campaign`` (IM-S, RLS-T) with the foreign key ``snapshot_file_id`` to
``file_object`` and the DB-03 trigger ``tg_access_review_campaign__transition``; T-PLT-41
``access_review_item`` (IM-S, RLS-T) with ``ux_access_review_item__membership`` (04
``ux_access_review_item``; NC-16 suffix, SPEC-Q-193), the foreign keys
``access_review_campaign_id``, ``membership_id`` to ``tenant_membership`` and ``reviewer_id`` to
``app_user``, the DB-03 trigger ``tg_access_review_item__transition`` and the DB-10 trigger
``tg_access_review_item__separation``.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops
from sqlalchemy.dialects.postgresql import JSONB

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

ACCESS_REVIEW_STATUS = ("DRAFT", "IN_REVIEW", "COMPLETED", "CANCELLED")
ACCESS_REVIEW_DECISION = ("PENDING", "CERTIFIED", "REVOKE_REQUESTED", "REVOKED")
# 04 T-PLT-40 and T-PLT-41: the columns erev_app may update.
CAMPAIGN_UPDATE_COLUMNS = (
    "status",
    "started_at",
    "completed_at",
    "snapshot_file_id",
    "updated_at",
    "updated_by",
    "updated_by_kind",
    "row_version",
)
ITEM_UPDATE_COLUMNS = (
    "decision",
    "reviewer_id",
    "decided_at",
    "comment",
    "revocation_completed_at",
    "updated_at",
    "updated_by",
    "updated_by_kind",
    "row_version",
)
# DB-03: erev_api.db.transitions.transition_trigger_sql(<table>) at PLF-28; DG-ARC-07 compares the
# installed functions with a fresh rendering.
CAMPAIGN_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['completed_at', 'row_version', 'snapshot_file_id', 'started_at', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.completed_at IS NOT NULL AND NEW.completed_at IS DISTINCT FROM OLD.completed_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: completed_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.snapshot_file_id IS NOT NULL AND NEW.snapshot_file_id IS DISTINCT FROM OLD.snapshot_file_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: snapshot_file_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.started_at IS NOT NULL AND NEW.started_at IS DISTINCT FROM OLD.started_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: started_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['DRAFT>CANCELLED', 'DRAFT>IN_REVIEW', 'IN_REVIEW>CANCELLED', 'IN_REVIEW>COMPLETED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501
ITEM_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['comment', 'decided_at', 'decision', 'reviewer_id', 'revocation_completed_at', 'row_version', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.comment IS NOT NULL AND NEW.comment IS DISTINCT FROM OLD.comment THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: comment of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.decided_at IS NOT NULL AND NEW.decided_at IS DISTINCT FROM OLD.decided_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: decided_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.reviewer_id IS NOT NULL AND NEW.reviewer_id IS DISTINCT FROM OLD.reviewer_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: reviewer_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.revocation_completed_at IS NOT NULL AND NEW.revocation_completed_at IS DISTINCT FROM OLD.revocation_completed_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: revocation_completed_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.decision IS DISTINCT FROM OLD.decision
     AND (OLD.decision::text || '>' || NEW.decision::text) <> ALL (ARRAY['PENDING>CERTIFIED', 'PENDING>REVOKE_REQUESTED', 'REVOKE_REQUESTED>REVOKED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: decision of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.decision, NEW.decision);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501
# DB-10: the reviewer is not the reviewed membership's user (EREV-APR-001). A row outside the
# tenant context is left to row-level security, which checks after BEFORE triggers.
ITEM_SEPARATION_BODY = """
BEGIN
  IF NEW.reviewer_id IS NULL OR NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id() THEN
    RETURN NEW;
  END IF;
  IF EXISTS (SELECT 1 FROM erev.tenant_membership m
              WHERE m.tenant_id = NEW.tenant_id AND m.id = NEW.membership_id
                AND m.user_id = NEW.reviewer_id) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-APR-001: the reviewer of access review item %s is the reviewed member',
                       NEW.id);
  END IF;
  RETURN NEW;
END
"""


def _timestamp(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("access_review_status", ACCESS_REVIEW_STATUS)
    ops.create_enum("access_review_decision", ACCESS_REVIEW_DECISION)

    ops.create_tenant_table(
        "access_review_campaign",
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column(
            "status",
            ops.NamedType("erev.access_review_status"),
            nullable=False,
            server_default=sa.text("'DRAFT'"),
        ),
        _timestamp("as_of", nullable=False),
        sa.Column("reviewer_membership_ids", sa.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("snapshot_file_id", sa.Uuid(), nullable=True),
        _timestamp("started_at"),
        _timestamp("completed_at"),
        standard_sets=["SC-C", "SC-M"],
    )
    ops.add_tenant_fk("access_review_campaign", "snapshot_file_id", "file_object")
    ops.apply_class("access_review_campaign", "IM-S", update_columns=CAMPAIGN_UPDATE_COLUMNS)
    ops.enable_rls("access_review_campaign", "RLS-T")
    ops.create_trigger(
        "access_review_campaign",
        "transition",
        CAMPAIGN_TRANSITION_BODY,
        timing="BEFORE",
        events="UPDATE",
    )

    ops.create_tenant_table(
        "access_review_item",
        sa.Column("access_review_campaign_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("user_email_snapshot", ops.NamedType("erev.email"), nullable=False),
        sa.Column("roles_snapshot", JSONB(), nullable=False),
        _timestamp("last_login_at"),
        sa.Column(
            "decision",
            ops.NamedType("erev.access_review_decision"),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("reviewer_id", sa.Uuid(), nullable=True),
        _timestamp("decided_at"),
        sa.Column("comment", ops.NamedType("erev.memo"), nullable=True),
        _timestamp("revocation_completed_at"),
        standard_sets=["SC-C", "SC-M"],
        unique=[
            (
                "ux_access_review_item__membership",
                ["tenant_id", "access_review_campaign_id", "membership_id"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("access_review_item", "access_review_campaign_id", "access_review_campaign")
    ops.add_tenant_fk("access_review_item", "membership_id", "tenant_membership")
    ops.add_global_fk("access_review_item", "reviewer_id", "app_user")
    ops.apply_class("access_review_item", "IM-S", update_columns=ITEM_UPDATE_COLUMNS)
    ops.enable_rls("access_review_item", "RLS-T")
    ops.create_trigger(
        "access_review_item",
        "separation",
        ITEM_SEPARATION_BODY,
        timing="BEFORE",
        events="INSERT OR UPDATE",
    )
    ops.create_trigger(
        "access_review_item",
        "transition",
        ITEM_TRANSITION_BODY,
        timing="BEFORE",
        events="UPDATE",
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("access_review_item")
    ops.drop_tenant_table("access_review_campaign")
    ops.drop_enum("access_review_decision")
    ops.drop_enum("access_review_status")
