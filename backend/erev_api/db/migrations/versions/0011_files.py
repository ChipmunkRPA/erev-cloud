"""BUILD_SPEC item PLF-8: files, attachments and upload safety.

04 ids created: E-68 ``file_purpose``; T-PLT-29 ``file_object`` (IM-A with the DB-03 update
allow-list, RLS-T) with ``ck_file_object__size_limit``, ``ux_file_object__sha_purpose`` and the
DB-03 trigger ``tg_file_object__transition``; T-PLT-30 ``file_attachment`` (IM-S, RLS-T) with
``ix_file_attachment__subject``, the DB-03 trigger ``tg_file_attachment__transition`` and the DB-11
trigger ``tg_file_attachment__void``.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

# 04 §3.4 E-68.
FILE_PURPOSE = (
    "IMPORT_SOURCE",
    "ATTACHMENT",
    "SSP_STUDY",
    "REPORT_OUTPUT",
    "EVIDENCE_PACK",
    "JOURNAL_EXPORT",
    "LEGACY_DATABASE",
    "SNAPSHOT_DATASET",
    "IMPACT_PREVIEW",
    "AI_PROMPT_LOG",
    "AUDIT_DIGEST",
    "POSTING_RESPONSE",
    "AI_DOCUMENT_TEXT",
)
# 04 T-PLT-29 and T-PLT-30: the columns erev_app may update.
FILE_OBJECT_UPDATE_COLUMNS = (
    "legal_hold",
    "retention_until",
    "shredded_at",
    "shredded_by",
    "shredded_by_kind",
    "shred_reason",
)
FILE_ATTACHMENT_UPDATE_COLUMNS = ("voided_at", "voided_by", "voided_by_kind", "void_reason")
SUBJECT_TYPES = (
    "contract",
    "modification",
    "estimate_version",
    "ssp_book_version",
    "judgement_record",
    "manual_adjustment",
    "reconciliation",
    "sod_exception",
    "approval_request",
    "exception_item",
    "contract_event",
    "event_submission",
)
# DB-03: erev_api.db.transitions.transition_trigger_sql(<table>) at PLF-8; DG-ARC-07 compares the
# installed functions with a fresh rendering.
FILE_OBJECT_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['legal_hold', 'retention_until', 'shred_reason', 'shredded_at', 'shredded_by', 'shredded_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.shred_reason IS NOT NULL AND NEW.shred_reason IS DISTINCT FROM OLD.shred_reason THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: shred_reason of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.shredded_at IS NOT NULL AND NEW.shredded_at IS DISTINCT FROM OLD.shredded_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: shredded_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.shredded_by IS NOT NULL AND NEW.shredded_by IS DISTINCT FROM OLD.shredded_by THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: shredded_by of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.shredded_by_kind IS NOT NULL AND NEW.shredded_by_kind IS DISTINCT FROM OLD.shredded_by_kind THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: shredded_by_kind of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501
FILE_ATTACHMENT_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['void_reason', 'voided_at', 'voided_by', 'voided_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.void_reason IS NOT NULL AND NEW.void_reason IS DISTINCT FROM OLD.void_reason THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: void_reason of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.voided_at IS NOT NULL AND NEW.voided_at IS DISTINCT FROM OLD.voided_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: voided_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.voided_by IS NOT NULL AND NEW.voided_by IS DISTINCT FROM OLD.voided_by THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: voided_by of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.voided_by_kind IS NOT NULL AND NEW.voided_by_kind IS DISTINCT FROM OLD.voided_by_kind THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: voided_by_kind of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501
# DB-11: a void is refused while an APPROVED approval request relies on the subject. The request
# table arrives later; until then no approval can exist, and the query is dynamic so the function
# compiles without it (SPEC-Q-160).
FILE_ATTACHMENT_VOID_BODY = """
DECLARE
  approved boolean := false;
BEGIN
  IF OLD.voided_at IS NULL AND NEW.voided_at IS NOT NULL
     AND to_regclass('erev.approval_request') IS NOT NULL THEN
    EXECUTE 'SELECT EXISTS (SELECT 1 FROM erev.approval_request r'
         || ' WHERE r.tenant_id = $1 AND r.status::text = ''APPROVED'''
         || ' AND (r.subject_id = $2 OR ($3 = ''approval_request'' AND r.id = $2)))'
       INTO approved USING NEW.tenant_id, NEW.subject_id, NEW.subject_type;
    IF approved THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-ATT-001: attachment %s of %I.%I cannot be voided while an '
                         'approved request relies on its subject',
                         NEW.id, TG_TABLE_SCHEMA, TG_TABLE_NAME);
    END IF;
  END IF;
  RETURN NEW;
END
"""
SIZE_LIMIT = (
    "(purpose NOT IN ('ATTACHMENT', 'SSP_STUDY') OR size_bytes <= 26214400)"
    " AND (purpose <> 'IMPORT_SOURCE' OR size_bytes <= 52428800)"
    " AND (purpose <> 'LEGACY_DATABASE' OR size_bytes <= 524288000)"
)


def _timestamp(name: str) -> sa.Column[Any]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("file_purpose", FILE_PURPOSE)

    ops.create_tenant_table(
        "file_object",
        sa.Column("sha256", ops.NamedType("erev.sha256"), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=True),
        sa.Column("purpose", ops.NamedType("erev.file_purpose"), nullable=False),
        sa.Column("storage_backend", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("retention_until", sa.Date(), nullable=True),
        sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        _timestamp("shredded_at"),
        sa.Column("shredded_by", sa.Uuid(), nullable=True),
        sa.Column("shredded_by_kind", ops.NamedType("erev.principal_kind"), nullable=True),
        sa.Column("shred_reason", ops.NamedType("erev.memo"), nullable=True),
        standard_sets=["SC-C"],
        checks=[
            ("ck_file_object__size_bytes", "size_bytes > 0"),
            ("ck_file_object__size_limit", SIZE_LIMIT),
            ("ck_file_object__storage_backend", "storage_backend IN ('local', 'gcs')"),
            (
                "ck_file_object__shredded",
                "(shredded_at IS NULL) = (shredded_by_kind IS NULL)"
                " AND (shredded_at IS NULL) = (shred_reason IS NULL)",
            ),
        ],
        unique=[("ux_file_object__sha_purpose", ["tenant_id", "sha256", "purpose"], None)],
    )
    ops.apply_class("file_object", "IM-A", update_columns=FILE_OBJECT_UPDATE_COLUMNS)
    ops.enable_rls("file_object", "RLS-T")
    ops.create_trigger(
        "file_object", "transition", FILE_OBJECT_TRANSITION_BODY, timing="BEFORE", events="UPDATE"
    )

    subject_types = ", ".join(f"'{subject}'" for subject in SUBJECT_TYPES)
    ops.create_tenant_table(
        "file_attachment",
        sa.Column("file_object_id", sa.Uuid(), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("description", ops.NamedType("erev.label"), nullable=True),
        _timestamp("voided_at"),
        sa.Column("voided_by", sa.Uuid(), nullable=True),
        sa.Column("voided_by_kind", ops.NamedType("erev.principal_kind"), nullable=True),
        sa.Column("void_reason", ops.NamedType("erev.memo"), nullable=True),
        standard_sets=["SC-C"],
        checks=[("ck_file_attachment__subject_type", f"subject_type IN ({subject_types})")],
        indexes=[
            ("ix_file_attachment__subject", ["tenant_id", "subject_type", "subject_id"], None)
        ],
    )
    ops.add_tenant_fk("file_attachment", "file_object_id", "file_object")
    ops.apply_class("file_attachment", "IM-S", update_columns=FILE_ATTACHMENT_UPDATE_COLUMNS)
    ops.enable_rls("file_attachment", "RLS-T")
    ops.create_trigger(
        "file_attachment",
        "transition",
        FILE_ATTACHMENT_TRANSITION_BODY,
        timing="BEFORE",
        events="UPDATE",
    )
    ops.create_trigger(
        "file_attachment",
        "void",
        FILE_ATTACHMENT_VOID_BODY,
        timing="BEFORE",
        events="UPDATE OF voided_at",
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("file_attachment")
    ops.drop_tenant_table("file_object")
    ops.drop_enum("file_purpose")
