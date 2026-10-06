"""BUILD_SPEC item CTR-15: obligation reads, SSP overrides and policy overrides.

04 ids created: T-CON-23 ``policy_override`` and its DB-03 function.

- T-CON-23 ``policy_override`` (IM-S, RLS-T): primary key ``(tenant_id, id)``; the 04 check of
  ``level`` named ``ck_policy_override__level``; ``ck_policy_override__status`` for the six allowed
  statuses of the column note; ``ux_policy_override__active`` and ``ix_policy_override__contract``;
  the foreign keys to ``contract``, ``obligation``, ``registry_parameter (code)``,
  ``approval_request`` and the row it supersedes. DB-03 ``tg_policy_override__transition``: editable
  while DRAFT, afterwards ``status``, ``approval_request_id``, ``approved_at`` and SC-M only, along
  E-12 (``erev_api.db.transitions``).

``judgement_record_id`` has no foreign key yet: T-CON-19 ``judgement_record`` belongs to a later
item, whose revision adds the key (DG-MIG-03; L4-2-Q-3). One function is added.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

TABLE = "policy_override"
_SC_M = ("updated_at", "updated_by", "updated_by_kind", "row_version")
# 04 T-CON-23 class IM-S: the columns granted for UPDATE (every editable column while DRAFT; the
# DB-03 trigger narrows them afterwards).
UPDATE_COLUMNS = (
    "value",
    "rationale",
    "judgement_record_id",
    "status",
    "content_sha256",
    "approval_request_id",
    "approved_at",
    *_SC_M,
)
LEVEL_CHECK = (
    "level IN ('CONTRACT','OBLIGATION') AND ((level = 'OBLIGATION') = (obligation_id IS NOT NULL))"
)
STATUS_CHECK = "status IN ('DRAFT','SUBMITTED','APPROVED','SUPERSEDED','REJECTED','WITHDRAWN')"
ACTIVE_INDEX = (
    "CREATE UNIQUE INDEX ux_policy_override__active ON erev.policy_override "
    "(tenant_id, contract_id, "
    "coalesce(obligation_id, '00000000-0000-0000-0000-000000000000'::uuid), policy_key) "
    "WHERE status = 'APPROVED'"
)

# DB-03: erev_api.db.transitions.transition_trigger_sql("policy_override") at CTR-15; DG-ARC-07
# compares the installed function with a fresh rendering.
TRANSITION_BODY = """
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
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'approved_at', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.approved_at IS NOT NULL AND NEW.approved_at IS DISTINCT FROM OLD.approved_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: approved_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['APPROVED>SUPERSEDED', 'DRAFT>SUBMITTED', 'REJECTED>DRAFT', 'SUBMITTED>APPROVED', 'SUBMITTED>REJECTED', 'SUBMITTED>WITHDRAWN', 'WITHDRAWN>DRAFT']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def _uuid(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _named(
    name: str, type_name: str, *, nullable: bool, default: str | None = None
) -> sa.Column[Any]:
    server_default = None if default is None else sa.text(default)
    return sa.Column(
        name, ops.NamedType(type_name), nullable=nullable, server_default=server_default
    )


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_tenant_table(
        TABLE,
        _uuid("contract_id", nullable=False),
        _uuid("obligation_id"),
        _named("level", "erev.registry_scope", nullable=False),
        sa.Column("policy_key", sa.Text(), nullable=False),
        _named("value", "jsonb", nullable=False),
        _named("rationale", "erev.memo", nullable=False),
        _uuid("judgement_record_id"),
        _named("status", "erev.config_status", nullable=False, default="'DRAFT'"),
        _named("content_sha256", "erev.sha256", nullable=True),
        _uuid("approval_request_id"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        _uuid("supersedes_id"),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            ("ck_policy_override__level", LEVEL_CHECK),
            ("ck_policy_override__status", STATUS_CHECK),
        ],
        indexes=[("ix_policy_override__contract", ["tenant_id", "contract_id", "status"], None)],
    )
    ops.execute(ACTIVE_INDEX)
    ops.add_tenant_fk(TABLE, "contract_id", "contract")
    ops.add_tenant_fk(TABLE, "obligation_id", "obligation")
    ops.add_global_fk(TABLE, "policy_key", "registry_parameter", target_column="code")
    ops.add_tenant_fk(TABLE, "approval_request_id", "approval_request")
    ops.add_tenant_fk(TABLE, "supersedes_id", TABLE)
    ops.apply_class(TABLE, "IM-S", update_columns=UPDATE_COLUMNS)
    ops.enable_rls(TABLE, "RLS-T")
    ops.create_trigger(TABLE, "transition", TRANSITION_BODY, timing="BEFORE", events="UPDATE")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table(TABLE)
