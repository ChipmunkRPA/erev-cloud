"""BUILD_SPEC item PLF-14: transactional outbox, notifications and notification preferences.

04 ids created: E-69 ``notification_kind``; E-70 ``outbox_topic``; E-71 ``outbox_status``; T-INT-03
``outbox_message`` (IM-S, RLS-T), created in PLF by 04 §18 rule 7(a) (BS1-D-04), with
``ux_outbox_message__dedupe``, ``ix_outbox_message__due`` and the DB-03 trigger
``tg_outbox_message__transition``; T-PLT-24 ``notification`` (IM-S, RLS-T) with
``ix_notification__recipient`` and ``tg_notification__transition``; T-PLT-25
``notification_preference`` (IM-M, RLS-T) with ``ux_notification_preference__kind`` and
``ck_notification_preference__mandatory``.
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

# 04 §3.4 E-69 to E-71.
NOTIFICATION_KIND = (
    "APPROVAL_ASSIGNED",
    "ITEM_REJECTED",
    "APPROVAL_VOIDED",
    "JOB_FAILED",
    "CLOSE_BLOCKER_RAISED",
    "CHAIN_VERIFICATION_FAILED",
    "EXPORT_FAILED",
    "EXCEPTION_ASSIGNED",
    "SUPPORT_GRANT_REQUESTED",
    "ITEM_APPROVED",
    "PERIOD_LOCKED",
    "PERIOD_REOPENED",
)
OUTBOX_TOPIC = ("JOURNAL_EXPORT", "WEBHOOK", "EMAIL", "SYNC_REQUEST")
OUTBOX_STATUS = ("PENDING", "DISPATCHING", "DISPATCHED", "FAILED", "DEAD")
# 04 T-INT-03 and T-PLT-24: the columns erev_app may update.
OUTBOX_MESSAGE_UPDATE_COLUMNS = (
    "status",
    "attempt_count",
    "next_attempt_at",
    "last_error",
    "dispatched_at",
    "updated_at",
    "updated_by",
    "updated_by_kind",
    "row_version",
)
NOTIFICATION_UPDATE_COLUMNS = ("read_at", "email_sent_at")

# DB-03: erev_api.db.transitions.transition_trigger_sql(<table>) at PLF-14; DG-ARC-07 compares the
# installed functions with a fresh rendering.
OUTBOX_MESSAGE_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['attempt_count', 'dispatched_at', 'last_error', 'next_attempt_at', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.dispatched_at IS NOT NULL AND NEW.dispatched_at IS DISTINCT FROM OLD.dispatched_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: dispatched_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['DISPATCHING>DEAD', 'DISPATCHING>DISPATCHED', 'DISPATCHING>FAILED', 'FAILED>DISPATCHING', 'PENDING>DISPATCHING']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501
NOTIFICATION_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['email_sent_at', 'read_at']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.email_sent_at IS NOT NULL AND NEW.email_sent_at IS DISTINCT FROM OLD.email_sent_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: email_sent_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.read_at IS NOT NULL AND NEW.read_at IS DISTINCT FROM OLD.read_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: read_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def _named(name: str) -> ops.NamedType:
    return ops.NamedType(name)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("notification_kind", NOTIFICATION_KIND)
    ops.create_enum("outbox_topic", OUTBOX_TOPIC)
    ops.create_enum("outbox_status", OUTBOX_STATUS)

    timestamp = sa.DateTime(timezone=True)
    ops.create_tenant_table(
        "notification",
        sa.Column("recipient_membership_id", sa.Uuid(), nullable=False),
        sa.Column("kind", _named("erev.notification_kind"), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=True),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("title", _named("erev.label"), nullable=False),
        sa.Column("body", _named("erev.memo"), nullable=True),
        sa.Column("link_path", sa.Text(), nullable=True),
        sa.Column("read_at", timestamp, nullable=True),
        sa.Column("email_sent_at", timestamp, nullable=True),
        standard_sets=["SC-C"],
        indexes=[
            (
                "ix_notification__recipient",
                ["tenant_id", "recipient_membership_id", "read_at", "created_at"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("notification", "recipient_membership_id", "tenant_membership")
    ops.apply_class("notification", "IM-S", update_columns=NOTIFICATION_UPDATE_COLUMNS)
    ops.enable_rls("notification", "RLS-T")
    ops.create_trigger(
        "notification", "transition", NOTIFICATION_TRANSITION_BODY, timing="BEFORE", events="UPDATE"
    )

    ops.create_tenant_table(
        "notification_preference",
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("kind", _named("erev.notification_kind"), nullable=False),
        sa.Column("in_app", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("email", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        standard_sets=["SC-M"],
        checks=[
            (
                "ck_notification_preference__mandatory",
                "kind <> 'CHAIN_VERIFICATION_FAILED' OR (in_app AND email)",
            )
        ],
        unique=[
            (
                "ux_notification_preference__kind",
                ["tenant_id", "membership_id", "kind"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("notification_preference", "membership_id", "tenant_membership")
    ops.apply_class("notification_preference", "IM-M")
    ops.enable_rls("notification_preference", "RLS-T")

    ops.create_tenant_table(
        "outbox_message",
        sa.Column("topic", _named("erev.outbox_topic"), nullable=False),
        sa.Column("aggregate_type", sa.Text(), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=False),
        sa.Column("payload", _named("jsonb"), nullable=False),
        sa.Column(
            "status",
            _named("erev.outbox_status"),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("next_attempt_at", timestamp, nullable=False, server_default=sa.text("now()")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("dispatched_at", timestamp, nullable=True),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            ("ck_outbox_message__attempt_count", "attempt_count >= 0"),
            ("ck_outbox_message__payload", "jsonb_typeof(payload) = 'object'"),
        ],
        unique=[("ux_outbox_message__dedupe", ["tenant_id", "topic", "dedupe_key"], None)],
        indexes=[("ix_outbox_message__due", ["tenant_id", "status", "next_attempt_at"], None)],
    )
    ops.apply_class("outbox_message", "IM-S", update_columns=OUTBOX_MESSAGE_UPDATE_COLUMNS)
    ops.enable_rls("outbox_message", "RLS-T")
    ops.create_trigger(
        "outbox_message",
        "transition",
        OUTBOX_MESSAGE_TRANSITION_BODY,
        timing="BEFORE",
        events="UPDATE",
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("outbox_message")
    ops.drop_tenant_table("notification_preference")
    ops.drop_tenant_table("notification")
    ops.drop_enum("outbox_status")
    ops.drop_enum("outbox_topic")
    ops.drop_enum("notification_kind")
