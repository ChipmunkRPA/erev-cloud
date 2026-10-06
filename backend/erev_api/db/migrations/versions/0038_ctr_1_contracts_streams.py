"""BUILD_SPEC item CTR-1: contract headers, combination groups and event streams.

04 ids created: E-03 ``contract_event_type``, E-17 ``contract_status``, E-26 ``modification_status``
and E-95 ``combination_status``.

- T-CON-03 ``combination_group`` (IM-S, RLS-T): ``ux_combination_group__code``,
  ``ix_combination_group__dirty``, the checks ``ck_combination_group__criterion`` and
  ``ck_combination_group__criterion_required``, the foreign keys to ``currency`` and
  ``approval_request``, and the DB-03 trigger ``tg_combination_group__transition``.
- T-CON-01 ``contract`` (IM-X, RLS-TE on ``contracting_entity_id``): ``ux_contract__no``,
  ``ux_contract__external_id``, ``ix_contract__customer``, ``ix_contract__status``,
  ``ix_contract__group``, the checks ``ck_contract__termination_party``,
  ``ck_contract__termination_notice_days`` and ``ck_contract__head_stream_version``, the foreign
  keys to ``customer``, ``legal_entity``, ``currency``, ``combination_group`` and itself, and DB-18
  ``tg_contract__projection`` (``EREV-CON-001``).
- T-CON-05 ``contract_event`` (IM-A, RLS-TE on ``contracting_entity_id``):
  ``ux_contract_event__stream``, ``ux_contract_event__idempotency``, ``ix_contract_event__order``,
  ``ix_contract_event__recorded``, ``ix_contract_event__type``, the checks
  ``ck_contract_event__stream_version``, ``ck_contract_event__origin`` and
  ``ck_contract_event__supersedes``, the foreign keys to ``contract``, ``legal_entity``,
  ``approval_request`` and itself, DB-01, and DB-08
  ``tg_contract_event__insert`` (``EREV-EVT-001``) over the sequence
  ``erev.contract_event_record_seq`` of revision 0001.
- T-CON-04 ``combination_group_member`` (IM-S, RLS-T): ``ux_combination_group_member__current``,
  ``ix_combination_group_member__group``, the foreign keys to the group, the contract and the join
  and leave events, and the DB-03 trigger ``tg_combination_group_member__transition``.
- T-CON-10 ``obligation`` (IM-A, RLS-T): ``ux_obligation__key``, ``ix_obligation__product``, DB-01,
  and the foreign keys to ``contract``, ``product``, ``contract_event`` and itself.
- T-CON-24 ``event_submission`` (IM-S, RLS-TE on ``contracting_entity_id``):
  ``ix_event_submission__contract``, ``ck_event_submission__events``, the foreign keys to
  ``contract``, ``legal_entity`` and ``approval_request``, and the DB-03 trigger
  ``tg_event_submission__transition``.

The checks and foreign keys 04 does not name are L3-1-Q-13. The foreign keys to tables of later
revisions (``contract.latest_computation_id``, ``combination_group.judgement_record_id`` and
``head_computation_id``, and ``contract_event.modification_id``, ``estimate_version_id``,
``manual_adjustment_id``, ``import_upload_id``, ``source_record_id`` and ``sync_run_id``) belong to
those revisions (DG-MIG-03). Five functions are added.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None

# 04 §3.3 E-03 and §3.4 E-17, E-26, E-95 (DG-MIG-06).
CONTRACT_EVENT_TYPE = (
    "CONTRACT_BOOKED",
    "CONTRACT_ACTIVATED",
    "COLLECTIBILITY_ASSESSED",
    "CONTRACT_CRITERIA_MET",
    "CONTRACT_AMENDED",
    "DELIVERY_RECORDED",
    "PROGRESS_RECORDED",
    "MILESTONE_ACHIEVED",
    "USAGE_REPORTED",
    "COST_INCURRED",
    "BILLING_RECORDED",
    "CREDIT_MEMO_RECORDED",
    "PAYMENT_RECEIVED",
    "RETURN_RECORDED",
    "ESTIMATE_CHANGED",
    "MATERIAL_RIGHT_EXERCISED",
    "MATERIAL_RIGHT_EXPIRED",
    "HOLD_APPLIED",
    "HOLD_RELEASED",
    "PRE_STANDARD_REVENUE_RECORDED",
    "MANUAL_ADJUSTMENT_APPLIED",
    "CONTRACT_TERMINATED",
    "COMBINATION_CHANGED",
    "OPENING_BALANCE_ESTABLISHED",
    "EVENT_VOIDED",
    "CONTRACT_VOIDED",
    "SIGNIFICANT_CHANGE_FLAGGED",
    "LINE_ATTRIBUTES_CHANGED",
    "MEMO_UPDATED",
    "REGROUPED",
)
CONTRACT_STATUS = (
    "DRAFT",
    "PENDING_REVIEW",
    "NOT_A_CONTRACT",
    "ACTIVE",
    "COMPLETED",
    "TERMINATED",
    "VOIDED",
)
MODIFICATION_STATUS = ("DRAFT", "SUBMITTED", "APPROVED", "APPLIED", "REJECTED", "VOIDED")
COMBINATION_STATUS = ("PROPOSED", "SUBMITTED", "APPROVED", "APPLIED", "REJECTED")
_SC_M = ("updated_at", "updated_by", "updated_by_kind", "row_version")
# 04 T-CON-03, T-CON-04 and T-CON-24 IM-S: the columns erev_app may update. [J] L3-1-Q-13: while
# DRAFT an event submission's events, comment and hash change; its contract and entity never do.
GROUP_UPDATE_COLUMNS = (
    "status",
    "criterion",
    "rationale",
    "judgement_record_id",
    "approval_request_id",
    "inception_date",
    "head_computation_id",
    "dirty_since",
    *_SC_M,
)
MEMBER_UPDATE_COLUMNS = ("valid_to_known_at", "leave_event_id")
SUBMISSION_UPDATE_COLUMNS = (
    "events",
    "status",
    "comment",
    "content_sha256",
    "approval_request_id",
    "applied_event_ids",
    *_SC_M,
)

# DB-03: erev_api.db.transitions.transition_trigger_sql(<table>) at CTR-1; DG-ARC-07 compares the
# installed functions with a fresh rendering.
GROUP_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'criterion', 'dirty_since', 'head_computation_id', 'inception_date', 'judgement_record_id', 'rationale', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>APPLIED', 'PROPOSED>SUBMITTED', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501
MEMBER_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['leave_event_id', 'valid_to_known_at']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.leave_event_id IS NOT NULL AND NEW.leave_event_id IS DISTINCT FROM OLD.leave_event_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: leave_event_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.valid_to_known_at IS NOT NULL AND NEW.valid_to_known_at IS DISTINCT FROM OLD.valid_to_known_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: valid_to_known_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501
SUBMISSION_TRANSITION_BODY = """
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
   WHERE n.key <> ALL (ARRAY['applied_event_ids', 'approval_request_id', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>APPLIED', 'DRAFT>SUBMITTED', 'DRAFT>VOIDED', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED', 'SUBMITTED>VOIDED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

# DB-18: while head_stream_version does not rise, only the SC-M columns, latest_computation_id and
# combination_group_id change; a lower head is a change of an unlisted column.
CONTRACT_PROJECTION_BODY = """
DECLARE
  old_row jsonb;
  new_row jsonb;
  changed text;
BEGIN
  IF NEW.head_stream_version > OLD.head_stream_version THEN
    RETURN NEW;
  END IF;
  old_row := to_jsonb(OLD);
  new_row := to_jsonb(NEW);
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['combination_group_id', 'latest_computation_id', 'row_version', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-CON-001: columns %s of %I.%I row %s change without an appended event',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.id);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

# DB-08: record_seq from the sequence and recorded_at = now(); the version is at most the contract's
# head and follows its predecessor; the entity is the contract's. A row outside the tenant context
# or the entity scope is left to row-level security, which checks after BEFORE triggers.
EVENT_INSERT_BODY = """
DECLARE
  head integer;
  entity uuid;
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id()
     OR NOT coalesce(erev.entity_in_scope(NEW.contracting_entity_id), false) THEN
    RETURN NEW;
  END IF;
  NEW.record_seq := nextval('erev.contract_event_record_seq');
  NEW.recorded_at := now();
  SELECT c.head_stream_version, c.contracting_entity_id INTO head, entity
    FROM erev.contract c
   WHERE c.tenant_id = NEW.tenant_id AND c.id = NEW.contract_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-EVT-001: %I.%I row %s names no visible contract %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, NEW.id, NEW.contract_id);
  END IF;
  IF NEW.contracting_entity_id IS DISTINCT FROM entity THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-EVT-001: contracting_entity_id of %I.%I row %s differs from the '
                       'contract''s', TG_TABLE_SCHEMA, TG_TABLE_NAME, NEW.id);
  END IF;
  IF NEW.stream_version > head THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-EVT-001: stream_version %s of contract %s is above the head %s',
                       NEW.stream_version, NEW.contract_id, head);
  END IF;
  IF NEW.stream_version > 1 AND NOT EXISTS (
    SELECT 1 FROM erev.contract_event e
     WHERE e.tenant_id = NEW.tenant_id AND e.contract_id = NEW.contract_id
       AND e.stream_version = NEW.stream_version - 1
  ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-EVT-001: stream_version %s of contract %s follows no version %s',
                       NEW.stream_version, NEW.contract_id, NEW.stream_version - 1);
  END IF;
  RETURN NEW;
END
"""


def _uuid(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _text(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Text(), nullable=nullable)


def _timestamp(name: str, *, nullable: bool = True, now_default: bool = False) -> sa.Column[Any]:
    default = sa.text("now()") if now_default else None
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable, server_default=default)


def _named(
    name: str, type_name: str, *, nullable: bool, default: str | None = None
) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(
        name, ops.NamedType(type_name), nullable=nullable, server_default=server_default
    )


def _boolean(name: str, *, default: str | None = None, nullable: bool = False) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(name, sa.Boolean(), nullable=nullable, server_default=server_default)


def _create_combination_group() -> None:
    ops.create_tenant_table(
        "combination_group",
        _text("code", nullable=False),
        _boolean("is_singleton"),
        _named("status", "erev.combination_status", nullable=False),
        _named("transaction_currency", "erev.currency_code", nullable=False),
        _text("criterion"),
        _named("rationale", "erev.memo", nullable=True),
        _uuid("judgement_record_id"),
        _uuid("approval_request_id"),
        sa.Column("inception_date", sa.Date(), nullable=False),
        _uuid("head_computation_id"),
        _timestamp("dirty_since"),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            ("ck_combination_group__criterion", "criterion IN ('25_9_A', '25_9_B', '25_9_C')"),
            ("ck_combination_group__criterion_required", "is_singleton OR criterion IS NOT NULL"),
        ],
        unique=[("ux_combination_group__code", ["tenant_id", "code"], None)],
        indexes=[
            (
                "ix_combination_group__dirty",
                ["tenant_id", "dirty_since"],
                "dirty_since IS NOT NULL",
            )
        ],
    )
    ops.add_global_fk("combination_group", "transaction_currency", "currency", target_column="code")
    ops.add_tenant_fk("combination_group", "approval_request_id", "approval_request")
    ops.apply_class("combination_group", "IM-S", update_columns=GROUP_UPDATE_COLUMNS)
    ops.enable_rls("combination_group", "RLS-T")
    ops.create_trigger(
        "combination_group", "transition", GROUP_TRANSITION_BODY, timing="BEFORE", events="UPDATE"
    )


def _create_contract() -> None:
    ops.create_tenant_table(
        "contract",
        _text("contract_no", nullable=False),
        _text("external_id", nullable=False),
        _uuid("customer_id", nullable=False),
        _uuid("contracting_entity_id", nullable=False),
        _named("transaction_currency", "erev.currency_code", nullable=False),
        sa.Column("inception_date", sa.Date(), nullable=False),
        _named("status", "erev.contract_status", nullable=False, default="'DRAFT'"),
        _uuid("combination_group_id", nullable=False),
        sa.Column("head_stream_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        _uuid("latest_computation_id"),
        sa.Column("signature_date", sa.Date(), nullable=True),
        _text("document_ref"),
        _text("payment_terms"),
        _text("termination_party"),
        _boolean("termination_has_penalty", nullable=True),
        sa.Column("termination_notice_days", sa.Integer(), nullable=True),
        _boolean("has_commercial_substance", default="true"),
        _text("region"),
        _text("channel"),
        _text("contract_type"),
        _text("memo_1"),
        _text("memo_2"),
        _text("memo_3"),
        _named("custom_attributes", "jsonb", nullable=False, default="'{}'::jsonb"),
        _named("activation_checklist", "jsonb", nullable=True),
        _timestamp("activated_at"),
        _timestamp("completed_at"),
        _timestamp("terminated_at"),
        _timestamp("voided_at"),
        _uuid("renewal_of_contract_id"),
        _uuid("portfolio_id"),
        _boolean("scope_605_35", default="false"),
        _named("source_system", "erev.source_system", nullable=False),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            (
                "ck_contract__termination_party",
                "termination_party IN ('NONE', 'CUSTOMER', 'ENTITY', 'BOTH')",
            ),
            ("ck_contract__termination_notice_days", "termination_notice_days >= 0"),
            ("ck_contract__head_stream_version", "head_stream_version >= 0"),
        ],
        unique=[
            ("ux_contract__no", ["tenant_id", "contract_no"], None),
            ("ux_contract__external_id", ["tenant_id", "external_id"], None),
        ],
        indexes=[
            ("ix_contract__customer", ["tenant_id", "customer_id"], None),
            ("ix_contract__status", ["tenant_id", "status"], None),
            ("ix_contract__group", ["tenant_id", "combination_group_id"], None),
        ],
    )
    ops.add_tenant_fk("contract", "customer_id", "customer")
    ops.add_tenant_fk("contract", "contracting_entity_id", "legal_entity")
    ops.add_global_fk("contract", "transaction_currency", "currency", target_column="code")
    ops.add_tenant_fk("contract", "combination_group_id", "combination_group")
    ops.add_tenant_fk("contract", "renewal_of_contract_id", "contract")
    ops.apply_class("contract", "IM-X")
    ops.enable_rls("contract", "RLS-TE", entity_column="contracting_entity_id")
    ops.create_trigger(
        "contract", "projection", CONTRACT_PROJECTION_BODY, timing="BEFORE", events="UPDATE"
    )


def _create_contract_event() -> None:
    ops.create_tenant_table(
        "contract_event",
        _uuid("contract_id", nullable=False),
        _uuid("contracting_entity_id", nullable=False),
        sa.Column("stream_version", sa.Integer(), nullable=False),
        _named("event_type", "erev.contract_event_type", nullable=False),
        sa.Column("schema_version", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("effective_date", sa.Date(), nullable=False),
        _timestamp("recorded_at", nullable=False, now_default=True),
        sa.Column(
            "record_seq",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("nextval('erev.contract_event_record_seq')"),
        ),
        _text("origin", nullable=False),
        _boolean("is_manual", default="false"),
        _named("obligation_ids", "uuid[]", nullable=False, default="'{}'::uuid[]"),
        _named("payload", "jsonb", nullable=False),
        _named("payload_sha256", "erev.sha256", nullable=False),
        _text("idempotency_key"),
        _uuid("supersedes_event_id"),
        _uuid("approval_request_id"),
        _uuid("modification_id"),
        _uuid("estimate_version_id"),
        _uuid("manual_adjustment_id"),
        _uuid("import_upload_id"),
        _uuid("source_record_id"),
        _uuid("sync_run_id"),
        _text("request_id", nullable=False),
        standard_sets=["SC-C"],
        checks=[
            ("ck_contract_event__stream_version", "stream_version >= 1"),
            (
                "ck_contract_event__origin",
                "origin IN ('API', 'UI', 'IMPORT', 'ADAPTER', 'SYSTEM', 'MIGRATION')",
            ),
            (
                "ck_contract_event__supersedes",
                "(event_type = 'EVENT_VOIDED') = (supersedes_event_id IS NOT NULL)",
            ),
        ],
        unique=[
            ("ux_contract_event__stream", ["tenant_id", "contract_id", "stream_version"], None),
            (
                "ux_contract_event__idempotency",
                ["tenant_id", "contract_id", "idempotency_key"],
                "idempotency_key IS NOT NULL",
            ),
        ],
        indexes=[
            (
                "ix_contract_event__order",
                ["tenant_id", "contract_id", "effective_date", "record_seq"],
                None,
            ),
            ("ix_contract_event__recorded", ["tenant_id", "recorded_at"], None),
            ("ix_contract_event__type", ["tenant_id", "event_type", "effective_date"], None),
        ],
    )
    ops.add_tenant_fk("contract_event", "contract_id", "contract")
    ops.add_tenant_fk("contract_event", "contracting_entity_id", "legal_entity")
    ops.add_tenant_fk("contract_event", "supersedes_event_id", "contract_event")
    ops.add_tenant_fk("contract_event", "approval_request_id", "approval_request")
    ops.apply_class("contract_event", "IM-A")
    ops.enable_rls("contract_event", "RLS-TE", entity_column="contracting_entity_id")
    ops.create_trigger(
        "contract_event", "insert", EVENT_INSERT_BODY, timing="BEFORE", events="INSERT"
    )


def _create_combination_group_member() -> None:
    ops.create_tenant_table(
        "combination_group_member",
        _uuid("combination_group_id", nullable=False),
        _uuid("contract_id", nullable=False),
        _timestamp("valid_from_known_at", nullable=False),
        _timestamp("valid_to_known_at"),
        _uuid("join_event_id", nullable=False),
        _uuid("leave_event_id"),
        standard_sets=["SC-C"],
        unique=[
            (
                "ux_combination_group_member__current",
                ["tenant_id", "contract_id"],
                "valid_to_known_at IS NULL",
            )
        ],
        indexes=[
            ("ix_combination_group_member__group", ["tenant_id", "combination_group_id"], None)
        ],
    )
    ops.add_tenant_fk("combination_group_member", "combination_group_id", "combination_group")
    ops.add_tenant_fk("combination_group_member", "contract_id", "contract")
    ops.add_tenant_fk("combination_group_member", "join_event_id", "contract_event")
    ops.add_tenant_fk("combination_group_member", "leave_event_id", "contract_event")
    ops.apply_class("combination_group_member", "IM-S", update_columns=MEMBER_UPDATE_COLUMNS)
    ops.enable_rls("combination_group_member", "RLS-T")
    ops.create_trigger(
        "combination_group_member",
        "transition",
        MEMBER_TRANSITION_BODY,
        timing="BEFORE",
        events="UPDATE",
    )


def _create_obligation() -> None:
    ops.create_tenant_table(
        "obligation",
        _uuid("contract_id", nullable=False),
        _text("obligation_key", nullable=False),
        _uuid("product_id", nullable=False),
        _text("legacy_record_key", nullable=False),
        _uuid("created_by_event_id", nullable=False),
        _uuid("parent_obligation_id"),
        _uuid("regrouped_from_obligation_id"),
        sa.Column("line_sequence", sa.Integer(), nullable=False),
        standard_sets=["SC-C"],
        unique=[("ux_obligation__key", ["tenant_id", "contract_id", "obligation_key"], None)],
        indexes=[("ix_obligation__product", ["tenant_id", "product_id"], None)],
    )
    ops.add_tenant_fk("obligation", "contract_id", "contract")
    ops.add_tenant_fk("obligation", "product_id", "product")
    ops.add_tenant_fk("obligation", "created_by_event_id", "contract_event")
    ops.add_tenant_fk("obligation", "parent_obligation_id", "obligation")
    ops.add_tenant_fk("obligation", "regrouped_from_obligation_id", "obligation")
    ops.apply_class("obligation", "IM-A")
    ops.enable_rls("obligation", "RLS-T")


def _create_event_submission() -> None:
    ops.create_tenant_table(
        "event_submission",
        _uuid("contract_id", nullable=False),
        _uuid("contracting_entity_id", nullable=False),
        _named("events", "jsonb", nullable=False),
        _named("status", "erev.modification_status", nullable=False, default="'DRAFT'"),
        _named("comment", "erev.memo", nullable=True),
        _named("content_sha256", "erev.sha256", nullable=True),
        _uuid("approval_request_id"),
        _named("applied_event_ids", "uuid[]", nullable=False, default="'{}'::uuid[]"),
        standard_sets=["SC-C", "SC-M"],
        checks=[("ck_event_submission__events", "jsonb_typeof(events) = 'array'")],
        indexes=[("ix_event_submission__contract", ["tenant_id", "contract_id", "status"], None)],
    )
    ops.add_tenant_fk("event_submission", "contract_id", "contract")
    ops.add_tenant_fk("event_submission", "contracting_entity_id", "legal_entity")
    ops.add_tenant_fk("event_submission", "approval_request_id", "approval_request")
    ops.apply_class("event_submission", "IM-S", update_columns=SUBMISSION_UPDATE_COLUMNS)
    ops.enable_rls("event_submission", "RLS-TE", entity_column="contracting_entity_id")
    ops.create_trigger(
        "event_submission",
        "transition",
        SUBMISSION_TRANSITION_BODY,
        timing="BEFORE",
        events="UPDATE",
    )


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("contract_event_type", CONTRACT_EVENT_TYPE)
    ops.create_enum("contract_status", CONTRACT_STATUS)
    ops.create_enum("modification_status", MODIFICATION_STATUS)
    ops.create_enum("combination_status", COMBINATION_STATUS)
    _create_combination_group()
    _create_contract()
    _create_contract_event()
    _create_combination_group_member()
    _create_obligation()
    _create_event_submission()


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("event_submission")
    ops.drop_tenant_table("obligation")
    ops.drop_tenant_table("combination_group_member")
    ops.drop_tenant_table("contract_event")
    ops.drop_tenant_table("contract")
    ops.drop_tenant_table("combination_group")
    ops.drop_enum("combination_status")
    ops.drop_enum("modification_status")
    ops.drop_enum("contract_status")
    ops.drop_enum("contract_event_type")
