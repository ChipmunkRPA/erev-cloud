"""BUILD_SPEC item PLF-24: outbound webhooks.

04 ids created: E-97 ``webhook_delivery_status``; T-PLT-35 ``webhook_endpoint`` (IM-M, RLS-T) with
``ck_webhook_endpoint__url`` and ``ck_webhook_endpoint__event_kinds``; T-PLT-36 ``webhook_delivery``
(IM-S, RLS-T) with ``ck_webhook_delivery__attempt_count``, ``ck_webhook_delivery__payload``,
``ix_webhook_delivery__due``, the composite foreign key ``webhook_endpoint_id`` to
``webhook_endpoint`` and the DB-03 trigger ``tg_webhook_delivery__transition``.
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

# 04 §3.4 E-97.
WEBHOOK_DELIVERY_STATUS = ("PENDING", "SUCCEEDED", "FAILED", "ABANDONED")
# 04 T-PLT-35 ``event_kinds``.
EVENT_KINDS = (
    "run.completed",
    "import.committed",
    "period.locked",
    "journal_batch.exported",
    "journal_batch.acknowledged",
    "exception.raised",
)
# 04 T-PLT-36: the columns erev_app may update.
WEBHOOK_DELIVERY_UPDATE_COLUMNS = (
    "status",
    "attempt_count",
    "next_attempt_at",
    "last_response_status",
    "last_error",
    "succeeded_at",
)
URL_CHECK = r"url ~ '^https://' OR url ~ '^http://(127\.0\.0\.1|localhost)(:[0-9]+)?/'"

# DB-03: erev_api.db.transitions.transition_trigger_sql("webhook_delivery") at PLF-24; DG-ARC-07
# compares the installed function with a fresh rendering.
WEBHOOK_DELIVERY_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['attempt_count', 'last_error', 'last_response_status', 'next_attempt_at', 'status', 'succeeded_at']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.succeeded_at IS NOT NULL AND NEW.succeeded_at IS DISTINCT FROM OLD.succeeded_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: succeeded_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['FAILED>ABANDONED', 'FAILED>SUCCEEDED', 'PENDING>ABANDONED', 'PENDING>FAILED', 'PENDING>SUCCEEDED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("webhook_delivery_status", WEBHOOK_DELIVERY_STATUS)
    timestamp = sa.DateTime(timezone=True)
    kinds = ", ".join(f"'{kind}'" for kind in EVENT_KINDS)

    ops.create_tenant_table(
        "webhook_endpoint",
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("description", ops.NamedType("erev.label"), nullable=True),
        sa.Column("event_kinds", ops.NamedType("text[]"), nullable=False),
        sa.Column("secret_ciphertext", ops.NamedType("bytea"), nullable=False),
        sa.Column("secret_key_id", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            ("ck_webhook_endpoint__url", URL_CHECK),
            (
                "ck_webhook_endpoint__event_kinds",
                f"cardinality(event_kinds) > 0 AND event_kinds <@ ARRAY[{kinds}]::text[]",
            ),
        ],
    )
    ops.apply_class("webhook_endpoint", "IM-M")
    ops.enable_rls("webhook_endpoint", "RLS-T")

    ops.create_tenant_table(
        "webhook_delivery",
        sa.Column("webhook_endpoint_id", sa.Uuid(), nullable=False),
        sa.Column("event_kind", sa.Text(), nullable=False),
        sa.Column("payload", ops.NamedType("jsonb"), nullable=False),
        sa.Column("payload_sha256", ops.NamedType("erev.sha256"), nullable=False),
        sa.Column(
            "status",
            ops.NamedType("erev.webhook_delivery_status"),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("next_attempt_at", timestamp, nullable=True),
        sa.Column("abandon_at", timestamp, nullable=False),
        sa.Column("last_response_status", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("succeeded_at", timestamp, nullable=True),
        standard_sets=["SC-C"],
        checks=[
            ("ck_webhook_delivery__attempt_count", "attempt_count >= 0"),
            ("ck_webhook_delivery__payload", "jsonb_typeof(payload) = 'object'"),
        ],
        indexes=[("ix_webhook_delivery__due", ["tenant_id", "status", "next_attempt_at"], None)],
    )
    ops.add_tenant_fk("webhook_delivery", "webhook_endpoint_id", "webhook_endpoint")
    ops.apply_class("webhook_delivery", "IM-S", update_columns=WEBHOOK_DELIVERY_UPDATE_COLUMNS)
    ops.enable_rls("webhook_delivery", "RLS-T")
    ops.create_trigger(
        "webhook_delivery",
        "transition",
        WEBHOOK_DELIVERY_TRANSITION_BODY,
        timing="BEFORE",
        events="UPDATE",
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("webhook_delivery")
    ops.drop_tenant_table("webhook_endpoint")
    ops.drop_enum("webhook_delivery_status")
