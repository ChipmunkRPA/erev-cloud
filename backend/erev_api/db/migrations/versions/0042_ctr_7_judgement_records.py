"""BUILD_SPEC item CTR-7: judgement records and the contract status machine.

04 ids created: E-56 ``judgement_topic`` and E-57 ``judgement_status``; T-CON-19
``judgement_record``; DB-10 ``tg_judgement_record__review``; the DB-03 functions of
``judgement_record`` and ``contract`` (DG-SM-01).

- T-CON-19 ``judgement_record`` (IM-S, RLS-T): ``ux_judgement_record__no``,
  ``ix_judgement_record__subject``, ``ix_judgement_record__status``, the check
  ``ck_judgement_record__subject_type``, and the foreign keys to ``contract``,
  ``approval_request`` and itself (``supersedes_id``). The UPDATE grant lists the columns a DRAFT
  record may change and the review columns (T-CON-19 "editable while DRAFT").
- DB-10 ``tg_judgement_record__review`` (BEFORE INSERT OR UPDATE): a reviewer differs from the
  preparer (``EREV-APR-001``).
- DB-03 ``tg_judgement_record__transition`` (PRD SM-10) and ``tg_contract__transition`` (PRD
  SM-02), rendered by ``erev_api.db.transitions``.
- The foreign key ``combination_group.judgement_record_id`` left by revision 0038 (DG-MIG-03).

Three functions are added.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

TABLE = "judgement_record"
# 04 §3.4 E-56 and E-57 (DG-MIG-06).
JUDGEMENT_TOPIC = (
    "NOT_A_CONTRACT",
    "COLLECTIBILITY",
    "CONTRACT_TERM",
    "COMBINATION",
    "POB_DISTINCT_OVERRIDE",
    "SERIES_CLASSIFICATION",
    "PRINCIPAL_AGENT",
    "LICENCE_NATURE",
    "WARRANTY_TYPE",
    "CONSTRAINT",
    "SFC_ASSESSMENT",
    "MODIFICATION_TREATMENT_OVERRIDE",
    "SSP_OVERRIDE",
    "REPURCHASE_CLASSIFICATION",
    "ESTIMATE_VS_ERROR",
    "OTHER",
    "BILL_AND_HOLD",
)
JUDGEMENT_STATUS = ("DRAFT", "SUBMITTED", "REVIEWED", "REJECTED", "SUPERSEDED")
SUBJECT_TYPES = (
    "contract",
    "obligation",
    "combination_group",
    "modification",
    "estimate_version",
    "product",
    "registry_version",
    "migration_batch",
)
_SC_M = ("updated_at", "updated_by", "updated_by_kind", "row_version")
# T-CON-19: the columns of a DRAFT record, then the review columns.
UPDATE_COLUMNS = (
    "topic",
    "subject_type",
    "subject_id",
    "contract_id",
    "book_code",
    "conclusion",
    "rationale",
    "alternatives_considered",
    "codification_refs",
    "questionnaire",
    "status",
    "reviewer_id",
    "reviewed_at",
    "approval_request_id",
    "content_sha256",
    "supersedes_id",
    *_SC_M,
)

# DB-03: erev_api.db.transitions.transition_trigger_sql(<table>) at CTR-7; DG-ARC-07 compares the
# installed functions with a fresh rendering.
JUDGEMENT_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF OLD.status::text = ANY (ARRAY['DRAFT']::text[]) THEN
    RETURN NEW;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'reviewed_at', 'reviewer_id', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.reviewed_at IS NOT NULL AND NEW.reviewed_at IS DISTINCT FROM OLD.reviewed_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: reviewed_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.reviewer_id IS NOT NULL AND NEW.reviewer_id IS DISTINCT FROM OLD.reviewer_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: reviewer_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['DRAFT>SUBMITTED', 'REJECTED>DRAFT', 'REVIEWED>SUPERSEDED', 'SUBMITTED>REJECTED', 'SUBMITTED>REVIEWED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501
CONTRACT_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  IF OLD.status::text = ANY (ARRAY['DRAFT']::text[]) THEN
    RETURN NEW;
  END IF;
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['activated_at', 'activation_checklist', 'combination_group_id', 'completed_at', 'custom_attributes', 'head_stream_version', 'latest_computation_id', 'memo_1', 'memo_2', 'memo_3', 'row_version', 'scope_605_35', 'status', 'terminated_at', 'updated_at', 'updated_by', 'updated_by_kind', 'voided_at']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['ACTIVE>COMPLETED', 'ACTIVE>TERMINATED', 'ACTIVE>VOIDED', 'COMPLETED>ACTIVE', 'COMPLETED>VOIDED', 'DRAFT>NOT_A_CONTRACT', 'DRAFT>PENDING_REVIEW', 'DRAFT>VOIDED', 'NOT_A_CONTRACT>PENDING_REVIEW', 'NOT_A_CONTRACT>VOIDED', 'PENDING_REVIEW>ACTIVE', 'PENDING_REVIEW>DRAFT', 'PENDING_REVIEW>VOIDED', 'TERMINATED>VOIDED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

# DB-10: a judgement record is never reviewed by its preparer.
JUDGEMENT_REVIEW_BODY = """
BEGIN
  IF NEW.reviewer_id IS NOT NULL AND NEW.reviewer_id = NEW.created_by THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-APR-001: the preparer of judgement record %s cannot review it',
                       NEW.id);
  END IF;
  RETURN NEW;
END
"""


def _uuid(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _text(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Text(), nullable=nullable)


def _named(
    name: str, type_name: str, *, nullable: bool, default: str | None = None
) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(
        name, ops.NamedType(type_name), nullable=nullable, server_default=server_default
    )


def _create_judgement_record() -> None:
    subject_types = ", ".join(f"'{value}'" for value in SUBJECT_TYPES)
    ops.create_tenant_table(
        TABLE,
        _text("judgement_no", nullable=False),
        _named("topic", "erev.judgement_topic", nullable=False),
        _text("subject_type", nullable=False),
        _uuid("subject_id", nullable=False),
        _uuid("contract_id"),
        _named("book_code", "erev.book_code", nullable=True),
        _named("conclusion", "erev.memo", nullable=False),
        _named("rationale", "erev.memo", nullable=False),
        _named("alternatives_considered", "erev.memo", nullable=True),
        _named("codification_refs", "text[]", nullable=False, default="'{}'::text[]"),
        _named("questionnaire", "jsonb", nullable=True),
        _named("status", "erev.judgement_status", nullable=False, default="'DRAFT'"),
        _uuid("reviewer_id"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        _uuid("approval_request_id"),
        _named("content_sha256", "erev.sha256", nullable=True),
        _uuid("supersedes_id"),
        standard_sets=["SC-C", "SC-M"],
        checks=[("ck_judgement_record__subject_type", f"subject_type IN ({subject_types})")],
        unique=[("ux_judgement_record__no", ["tenant_id", "judgement_no"], None)],
        indexes=[
            (
                "ix_judgement_record__subject",
                ["tenant_id", "subject_type", "subject_id"],
                None,
            ),
            ("ix_judgement_record__status", ["tenant_id", "status"], None),
        ],
    )
    ops.add_tenant_fk(TABLE, "contract_id", "contract")
    ops.add_tenant_fk(TABLE, "approval_request_id", "approval_request")
    ops.add_tenant_fk(TABLE, "supersedes_id", TABLE)
    ops.apply_class(TABLE, "IM-S", update_columns=UPDATE_COLUMNS)
    ops.enable_rls(TABLE, "RLS-T")
    ops.create_trigger(
        TABLE, "review", JUDGEMENT_REVIEW_BODY, timing="BEFORE", events="INSERT OR UPDATE"
    )
    ops.create_trigger(
        TABLE, "transition", JUDGEMENT_TRANSITION_BODY, timing="BEFORE", events="UPDATE"
    )


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("judgement_topic", JUDGEMENT_TOPIC)
    ops.create_enum("judgement_status", JUDGEMENT_STATUS)
    _create_judgement_record()
    ops.add_tenant_fk("combination_group", "judgement_record_id", TABLE)
    ops.create_trigger(
        "contract", "transition", CONTRACT_TRANSITION_BODY, timing="BEFORE", events="UPDATE"
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.execute("DROP TRIGGER tg_contract__transition ON erev.contract")
    ops.execute("DROP FUNCTION erev.tg_contract__transition()")
    ops.execute(
        "ALTER TABLE erev.combination_group DROP CONSTRAINT fk_combination_group__judgement_record"
    )
    ops.drop_tenant_table(TABLE)
    ops.drop_enum("judgement_status")
    ops.drop_enum("judgement_topic")
