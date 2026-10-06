"""BUILD_SPEC item PLF-10: approval requests, steps, decisions and the self-approval block.

04 ids created: E-05 ``approval_request_status``; E-06 ``approval_step_status``; E-07
``approval_decision_kind``; E-08 ``approval_subject_type``; T-PLT-17 ``approval_request`` (IM-S,
RLS-TE on a nullable ``entity_id``) with ``ux_approval_request__no``,
``ux_approval_request__pending_subject``, ``ix_approval_request__status`` and the DB-03 trigger
``tg_approval_request__transition``; T-PLT-18 ``approval_step`` (IM-S, RLS-T) with
``ux_approval_step__request_step`` and ``tg_approval_step__transition``; T-PLT-21
``approval_delegation`` (IM-S, RLS-T) with ``ix_approval_delegation__delegate`` and
``tg_approval_delegation__transition``; T-PLT-20 ``approval_decision`` (IM-A, RLS-T) with
``ux_approval_decision__step_approver``, ``ix_approval_decision__approver`` and the DB-10 trigger
``tg_approval_decision__sod``; the foreign keys ``approval_request_id`` of ``role_assignment``,
``sod_rule`` and ``sod_exception``. DB-11 ``tg_file_attachment__void`` of revision 0011 takes effect
now that ``approval_request`` exists (SPEC-Q-160). The foreign keys to ``legal_entity``,
``rule_set_version`` and ``rule`` belong to the revisions that create their targets (DG-MIG-03).
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

# 04 §3.4 E-05 to E-08.
APPROVAL_REQUEST_STATUS = ("PENDING", "APPROVED", "REJECTED", "VOIDED", "WITHDRAWN")
APPROVAL_STEP_STATUS = ("WAITING", "ACTIVE", "APPROVED", "REJECTED", "SKIPPED", "VOIDED")
APPROVAL_DECISION_KIND = ("APPROVE", "REJECT", "AUTO_APPROVE")
APPROVAL_SUBJECT_TYPE = (
    "SSP_BOOK_VERSION",
    "SSP_OVERRIDE",
    "CONTRACT_ACTIVATION",
    "MODIFICATION",
    "MANUAL_EVENT",
    "ESTIMATE_VERSION",
    "MANUAL_ADJUSTMENT",
    "REGISTRY_VERSION",
    "RULE_SET_VERSION",
    "POB_TEMPLATE_VERSION",
    "ACCOUNT_MAPPING_VERSION",
    "FX_RATE_SET_VERSION",
    "ROLE_CHANGE",
    "ROLE_ASSIGNMENT",
    "SOD_EXCEPTION",
    "PERIOD_LOCK",
    "PERIOD_REOPEN",
    "IMPORT_COMMIT",
    "CONTRACT_VOID",
    "COMBINATION_GROUP",
    "JUDGEMENT_RECORD",
    "JOURNAL_RUN",
    "SUPPORT_GRANT",
    "AI_PROPOSAL_ACCEPTANCE",
    "PRINCIPAL_AGENT_CHANGE",
    "ATTRIBUTE_CHANGE",
    "EXCEPTION_WAIVER",
    "MIGRATION_PROMOTION",
    "MAPPING_PROFILE_VERSION",
    "POLICY_OVERRIDE",
)
# 04 T-PLT-17, T-PLT-18 and T-PLT-21: the columns erev_app may update.
APPROVAL_REQUEST_UPDATE_COLUMNS = (
    "status",
    "decided_at",
    "voided_at",
    "void_reason",
    "current_step_no",
)
APPROVAL_STEP_UPDATE_COLUMNS = ("status", "activated_at", "completed_at")
APPROVAL_DELEGATION_UPDATE_COLUMNS = ("revoked_at", "revoked_by", "revoked_by_kind")
VOID_REASONS = ("STALE_SUBJECT", "SUBJECT_VOIDED", "WITHDRAWN_BY_PREPARER")
# Tables created before approval_request that reference it (DG-MIG-03).
REFERRING_TABLES = ("role_assignment", "sod_rule", "sod_exception")

# DB-03: erev_api.db.transitions.transition_trigger_sql(<table>) at PLF-10; DG-ARC-07 compares the
# installed functions with a fresh rendering.
APPROVAL_REQUEST_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['current_step_no', 'decided_at', 'status', 'void_reason', 'voided_at']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.decided_at IS NOT NULL AND NEW.decided_at IS DISTINCT FROM OLD.decided_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: decided_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
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
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['PENDING>APPROVED', 'PENDING>REJECTED', 'PENDING>VOIDED', 'PENDING>WITHDRAWN']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501
APPROVAL_STEP_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['activated_at', 'completed_at', 'status']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.activated_at IS NOT NULL AND NEW.activated_at IS DISTINCT FROM OLD.activated_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: activated_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.completed_at IS NOT NULL AND NEW.completed_at IS DISTINCT FROM OLD.completed_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: completed_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['ACTIVE>APPROVED', 'ACTIVE>REJECTED', 'ACTIVE>VOIDED', 'WAITING>ACTIVE', 'WAITING>SKIPPED', 'WAITING>VOIDED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501
APPROVAL_DELEGATION_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['revoked_at', 'revoked_by', 'revoked_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS DISTINCT FROM OLD.revoked_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: revoked_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.revoked_by IS NOT NULL AND NEW.revoked_by IS DISTINCT FROM OLD.revoked_by THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: revoked_by of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.revoked_by_kind IS NOT NULL AND NEW.revoked_by_kind IS DISTINCT FROM OLD.revoked_by_kind THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: revoked_by_kind of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501
# DB-10: the request is PENDING with the decision's content hash (EREV-APR-003), the step belongs to
# it and is ACTIVE; a human approver is neither the preparer nor on behalf of the preparer
# (EREV-APR-001), has no earlier decision on the request, directly or through delegation
# (EREV-APR-002), and holds an ACTIVE membership. A request or step in another state and an inactive
# approver give EREV-TRN-001 (SPEC-Q-167). A row outside the tenant context is left to row-level
# security, which checks after BEFORE triggers.
APPROVAL_DECISION_SOD_BODY = """
DECLARE
  request_row record;
  step_status text;
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id() THEN
    RETURN NEW;
  END IF;
  SELECT r.status::text AS status, r.preparer_id, r.subject_content_sha256 INTO request_row
    FROM erev.approval_request r
   WHERE r.tenant_id = NEW.tenant_id AND r.id = NEW.approval_request_id;
  IF NOT FOUND OR request_row.status <> 'PENDING' THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: approval request %s is not pending', NEW.approval_request_id);
  END IF;
  IF NEW.subject_content_sha256 IS DISTINCT FROM request_row.subject_content_sha256 THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-APR-003: the subject of approval request %s changed after submission',
                       NEW.approval_request_id);
  END IF;
  SELECT s.status::text INTO step_status
    FROM erev.approval_step s
   WHERE s.tenant_id = NEW.tenant_id AND s.id = NEW.approval_step_id
     AND s.approval_request_id = NEW.approval_request_id;
  IF NOT FOUND OR step_status <> 'ACTIVE' THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: step %s of approval request %s is not active',
                       NEW.approval_step_id, NEW.approval_request_id);
  END IF;
  IF NEW.approver_id IS NOT NULL THEN
    IF NEW.approver_id = request_row.preparer_id
       OR NEW.on_behalf_of_id = request_row.preparer_id THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-APR-001: the preparer of approval request %s cannot approve it',
                         NEW.approval_request_id);
    END IF;
    IF EXISTS (SELECT 1 FROM erev.approval_decision d
                WHERE d.tenant_id = NEW.tenant_id
                  AND d.approval_request_id = NEW.approval_request_id
                  AND (d.approver_id IN (NEW.approver_id, NEW.on_behalf_of_id)
                       OR d.on_behalf_of_id IN (NEW.approver_id, NEW.on_behalf_of_id))) THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-APR-002: the approver already decided approval request %s',
                         NEW.approval_request_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM erev.tenant_membership m
                    WHERE m.tenant_id = NEW.tenant_id AND m.user_id = NEW.approver_id
                      AND m.status = 'ACTIVE') THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = format('EREV-TRN-001: the approver of approval request %s has no active '
                         'membership', NEW.approval_request_id);
    END IF;
  END IF;
  RETURN NEW;
END
"""


def _named(name: str) -> ops.NamedType:
    return ops.NamedType(name)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("approval_request_status", APPROVAL_REQUEST_STATUS)
    ops.create_enum("approval_step_status", APPROVAL_STEP_STATUS)
    ops.create_enum("approval_decision_kind", APPROVAL_DECISION_KIND)
    ops.create_enum("approval_subject_type", APPROVAL_SUBJECT_TYPE)

    timestamp = sa.DateTime(timezone=True)
    void_reasons = ", ".join(f"'{reason}'" for reason in VOID_REASONS)
    ops.create_tenant_table(
        "approval_request",
        sa.Column("request_no", sa.Text(), nullable=False),
        sa.Column("subject_type", _named("erev.approval_subject_type"), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("subject_row_version", sa.Integer(), nullable=True),
        sa.Column("subject_content_sha256", _named("erev.sha256"), nullable=False),
        sa.Column("summary", _named("erev.label"), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=True),
        sa.Column("amount_functional", _named("erev.money"), nullable=True),
        sa.Column("amount_currency", _named("erev.currency_code"), nullable=True),
        sa.Column("flags", sa.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("routing_rule_set_version_id", sa.Uuid(), nullable=True),
        sa.Column("routing_rule_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            _named("erev.approval_request_status"),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("current_step_no", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("preparer_id", sa.Uuid(), nullable=True),
        sa.Column("preparer_kind", _named("erev.principal_kind"), nullable=False),
        sa.Column("submitted_at", timestamp, nullable=False, server_default=sa.text("now()")),
        sa.Column("decided_at", timestamp, nullable=True),
        sa.Column("voided_at", timestamp, nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=True),
        sa.Column("impact_preview_file_id", sa.Uuid(), nullable=True),
        sa.Column("impact_preview_sha256", _named("erev.sha256"), nullable=True),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("comment", _named("erev.memo"), nullable=True),
        standard_sets=["SC-C"],
        checks=[
            (
                "ck_approval_request__amount",
                "(amount_functional IS NULL) = (amount_currency IS NULL)",
            ),
            (
                "ck_approval_request__preparer",
                "preparer_id IS NOT NULL OR preparer_kind = 'SYSTEM'",
            ),
            (
                "ck_approval_request__void_reason",
                f"void_reason IS NULL OR void_reason IN ({void_reasons})",
            ),
        ],
        unique=[
            ("ux_approval_request__no", ["tenant_id", "request_no"], None),
            (
                "ux_approval_request__pending_subject",
                ["tenant_id", "subject_type", "subject_id"],
                "status = 'PENDING'",
            ),
        ],
        indexes=[("ix_approval_request__status", ["tenant_id", "status", "submitted_at"], None)],
    )
    ops.add_tenant_fk("approval_request", "impact_preview_file_id", "file_object")
    ops.apply_class("approval_request", "IM-S", update_columns=APPROVAL_REQUEST_UPDATE_COLUMNS)
    ops.enable_rls("approval_request", "RLS-TE", entity_column="entity_id", entity_nullable=True)
    ops.create_trigger(
        "approval_request",
        "transition",
        APPROVAL_REQUEST_TRANSITION_BODY,
        timing="BEFORE",
        events="UPDATE",
    )
    for table in REFERRING_TABLES:
        ops.add_tenant_fk(table, "approval_request_id", "approval_request")

    ops.create_tenant_table(
        "approval_step",
        sa.Column("approval_request_id", sa.Uuid(), nullable=False),
        sa.Column("step_no", sa.Integer(), nullable=False),
        sa.Column("name", _named("erev.label"), nullable=False),
        sa.Column("required_permission", sa.Text(), nullable=False),
        sa.Column("required_role_id", sa.Uuid(), nullable=True),
        sa.Column("min_approvers", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "status",
            _named("erev.approval_step_status"),
            nullable=False,
            server_default=sa.text("'WAITING'"),
        ),
        sa.Column("activated_at", timestamp, nullable=True),
        sa.Column("completed_at", timestamp, nullable=True),
        checks=[
            ("ck_approval_step__step_no", "step_no >= 1"),
            ("ck_approval_step__min_approvers", "min_approvers BETWEEN 1 AND 5"),
        ],
        unique=[
            (
                "ux_approval_step__request_step",
                ["tenant_id", "approval_request_id", "step_no"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("approval_step", "approval_request_id", "approval_request")
    ops.add_global_fk("approval_step", "required_permission", "permission", target_column="code")
    ops.add_tenant_fk("approval_step", "required_role_id", "role")
    ops.apply_class("approval_step", "IM-S", update_columns=APPROVAL_STEP_UPDATE_COLUMNS)
    ops.enable_rls("approval_step", "RLS-T")
    ops.create_trigger(
        "approval_step",
        "transition",
        APPROVAL_STEP_TRANSITION_BODY,
        timing="BEFORE",
        events="UPDATE",
    )

    ops.create_tenant_table(
        "approval_delegation",
        sa.Column("delegator_membership_id", sa.Uuid(), nullable=False),
        sa.Column("delegate_membership_id", sa.Uuid(), nullable=False),
        sa.Column("permissions", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("valid_from", timestamp, nullable=False),
        sa.Column("valid_to", timestamp, nullable=False),
        sa.Column("reason", _named("erev.memo"), nullable=False),
        sa.Column("revoked_at", timestamp, nullable=True),
        sa.Column("revoked_by", sa.Uuid(), nullable=True),
        sa.Column("revoked_by_kind", _named("erev.principal_kind"), nullable=True),
        standard_sets=["SC-C"],
        checks=[
            (
                "ck_approval_delegation__distinct_memberships",
                "delegate_membership_id <> delegator_membership_id",
            ),
            (
                "ck_approval_delegation__validity",
                "valid_to > valid_from AND valid_to <= valid_from + interval '90 days'",
            ),
        ],
        indexes=[
            (
                "ix_approval_delegation__delegate",
                ["tenant_id", "delegate_membership_id", "valid_to"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("approval_delegation", "delegator_membership_id", "tenant_membership")
    ops.add_tenant_fk("approval_delegation", "delegate_membership_id", "tenant_membership")
    ops.apply_class(
        "approval_delegation", "IM-S", update_columns=APPROVAL_DELEGATION_UPDATE_COLUMNS
    )
    ops.enable_rls("approval_delegation", "RLS-T")
    ops.create_trigger(
        "approval_delegation",
        "transition",
        APPROVAL_DELEGATION_TRANSITION_BODY,
        timing="BEFORE",
        events="UPDATE",
    )

    ops.create_tenant_table(
        "approval_decision",
        sa.Column("approval_request_id", sa.Uuid(), nullable=False),
        sa.Column("approval_step_id", sa.Uuid(), nullable=False),
        sa.Column("decision", _named("erev.approval_decision_kind"), nullable=False),
        sa.Column("approver_id", sa.Uuid(), nullable=True),
        sa.Column("approver_kind", _named("erev.principal_kind"), nullable=False),
        sa.Column("delegation_id", sa.Uuid(), nullable=True),
        sa.Column("on_behalf_of_id", sa.Uuid(), nullable=True),
        sa.Column("auto_rule_set_version_id", sa.Uuid(), nullable=True),
        sa.Column("auto_rule_id", sa.Uuid(), nullable=True),
        sa.Column("subject_content_sha256", _named("erev.sha256"), nullable=False),
        sa.Column("impact_preview_sha256", _named("erev.sha256"), nullable=True),
        sa.Column("mfa_verified_at", timestamp, nullable=True),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column("comment", _named("erev.memo"), nullable=True),
        sa.Column("decided_at", timestamp, nullable=False, server_default=sa.text("now()")),
        checks=[
            (
                "ck_approval_decision__auto_system",
                "(decision = 'AUTO_APPROVE') = (approver_kind = 'SYSTEM')",
            ),
            ("ck_approval_decision__approver_kind", "approver_kind IN ('USER', 'SYSTEM')"),
            (
                "ck_approval_decision__approver",
                "(approver_id IS NULL) = (decision = 'AUTO_APPROVE')",
            ),
            (
                "ck_approval_decision__auto_rule",
                "decision <> 'AUTO_APPROVE' OR auto_rule_set_version_id IS NOT NULL",
            ),
            (
                "ck_approval_decision__mfa",
                "approver_kind <> 'USER' OR mfa_verified_at IS NOT NULL",
            ),
            ("ck_approval_decision__reject_comment", "decision <> 'REJECT' OR comment IS NOT NULL"),
        ],
        unique=[
            (
                "ux_approval_decision__step_approver",
                ["tenant_id", "approval_step_id", "approver_id"],
                "approver_id IS NOT NULL",
            )
        ],
        indexes=[
            (
                "ix_approval_decision__approver",
                ["tenant_id", "approver_id", "decided_at"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("approval_decision", "approval_request_id", "approval_request")
    ops.add_tenant_fk("approval_decision", "approval_step_id", "approval_step")
    ops.add_tenant_fk("approval_decision", "delegation_id", "approval_delegation")
    ops.apply_class("approval_decision", "IM-A")
    ops.enable_rls("approval_decision", "RLS-T")
    ops.create_trigger(
        "approval_decision", "sod", APPROVAL_DECISION_SOD_BODY, timing="BEFORE", events="INSERT"
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table("approval_decision")
    ops.drop_tenant_table("approval_delegation")
    ops.drop_tenant_table("approval_step")
    for table in reversed(REFERRING_TABLES):
        ops.execute(f"ALTER TABLE erev.{table} DROP CONSTRAINT fk_{table}__approval_request")
    ops.drop_tenant_table("approval_request")
    ops.drop_enum("approval_subject_type")
    ops.drop_enum("approval_decision_kind")
    ops.drop_enum("approval_step_status")
    ops.drop_enum("approval_request_status")
