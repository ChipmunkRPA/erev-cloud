"""BUILD_SPEC item CTR-12: estimates and estimate versions.

04 ids created: E-09 ``estimate_kind``, E-10 ``estimate_method``, T-CON-12 ``estimate``, T-CON-13
``estimate_version`` and its DB-03 function.

- T-CON-12 ``estimate`` (IM-A, RLS-T): primary key ``(tenant_id, id)``; the 04 checks named
  ``ck_estimate__scope`` (exactly one of contract and portfolio), ``ck_estimate__vc_element_type``,
  ``ck_estimate__direction``, ``ck_estimate__direction_concession``,
  ``ck_estimate__direction_kind`` and ``ck_estimate__allocation_target``; the 04 expression index
  ``ux_estimate__code``; the foreign keys to ``contract`` and ``obligation``. ``portfolio_id`` has
  no foreign key: CTR-13 creates ``portfolio`` and adds it (DG-MIG-03; BUILD_SPEC BSF-D-09).
- T-CON-13 ``estimate_version`` (IM-S, RLS-T): ``ux_estimate_version__no``,
  ``ix_estimate_version__status``; checks ``ck_estimate_version__status`` (the six allowed statuses
  of the column note), ``ck_estimate_version__parameters`` (a JSON object) and the V6 constraint
  range ``ck_estimate_version__constraint_range``; the foreign keys to ``estimate``,
  ``judgement_record``, ``approval_request``, ``currency (code)`` and the version it supersedes.
  DB-03 ``tg_estimate_version__transition``: editable while DRAFT, afterwards ``status``,
  ``approval_request_id``, ``applied_event_ids`` and SC-M only, along E-12
  (``erev_api.db.transitions``).
- The foreign key ``contract_event.estimate_version_id`` → ``estimate_version``, which revision 0038
  left to this revision (DG-MIG-03).

One function is added.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None

ESTIMATE = "estimate"
VERSION = "estimate_version"
_SC_M = ("updated_at", "updated_by", "updated_by_kind", "row_version")
# 04 E-09 and E-10 (rev 1.2 values).
ESTIMATE_KIND = (
    "VARIABLE_CONSIDERATION",
    "RETURN_RATE",
    "BREAKAGE",
    "EAC",
    "EXERCISE_LIKELIHOOD",
    "IMPLICIT_PRICE_CONCESSION",
    "RENEWAL_EXPECTATION",
    "ROYALTY_ACCRUAL",
    "EXPECTED_PURCHASES",
    "SHARE_BASED_CONSIDERATION",
)
ESTIMATE_METHOD = ("EXPECTED_VALUE", "MOST_LIKELY_AMOUNT", "ENTERED_AMOUNT", "RATE", "COST_BUILDUP")
VC_ELEMENT_TYPES = (
    "BONUS",
    "PENALTY",
    "PERFORMANCE_INCENTIVE",
    "REBATE",
    "VOLUME_TIER",
    "PRICE_PROTECTION",
    "SLA_CREDIT",
    "DISCOUNT",
    "RETURN",
    "REFUND",
    "IMPLICIT_PRICE_CONCESSION",
    "CLAIM",
    "UNPRICED_CHANGE_ORDER",
    "USAGE",
    "ROYALTY",
    "MILESTONE",
)
ESTIMATE_CHECKS = (
    ("ck_estimate__scope", "(contract_id IS NULL) <> (portfolio_id IS NULL)"),
    (
        "ck_estimate__vc_element_type",
        "vc_element_type IN (" + ", ".join(f"'{value}'" for value in VC_ELEMENT_TYPES) + ")",
    ),
    ("ck_estimate__direction", "direction IN ('INCREASE','DECREASE')"),
    (
        "ck_estimate__direction_concession",
        "estimate_kind <> 'IMPLICIT_PRICE_CONCESSION' OR direction = 'DECREASE'",
    ),
    (
        "ck_estimate__direction_kind",
        "estimate_kind IN ('VARIABLE_CONSIDERATION','IMPLICIT_PRICE_CONCESSION')"
        " OR direction = 'INCREASE'",
    ),
    (
        "ck_estimate__allocation_target",
        "allocation_target IN ('CONTRACT','OBLIGATIONS','INCREMENTS')",
    ),
)
CODE_INDEX = (
    "CREATE UNIQUE INDEX ux_estimate__code ON erev.estimate "
    "(tenant_id, coalesce(contract_id, portfolio_id), element_code)"
)
VERSION_CHECKS = (
    (
        "ck_estimate_version__status",
        "status IN ('DRAFT','SUBMITTED','APPROVED','SUPERSEDED','REJECTED','WITHDRAWN')",
    ),
    ("ck_estimate_version__parameters", "jsonb_typeof(parameters) = 'object'"),
    (
        "ck_estimate_version__constraint_range",
        "constrained_amount IS NULL OR unconstrained_amount IS NULL"
        " OR most_conservative_amount IS NULL"
        " OR constrained_amount BETWEEN least(most_conservative_amount, unconstrained_amount)"
        " AND greatest(most_conservative_amount, unconstrained_amount)",
    ),
)
# 04 T-CON-13 class IM-S: the columns granted for UPDATE (every editable column while DRAFT; the
# DB-03 trigger narrows them afterwards).
UPDATE_COLUMNS = (
    "effective_date",
    "scenarios",
    "parameters",
    "unconstrained_amount",
    "most_conservative_amount",
    "constrained_amount",
    "rate",
    "expected_total_amount",
    "expected_quantity",
    "amortization_months",
    "currency",
    "constraint_checklist",
    "rationale",
    "judgement_record_id",
    "status",
    "content_sha256",
    "approval_request_id",
    "applied_event_ids",
    "supersedes_version_id",
    *_SC_M,
)

# DB-03: erev_api.db.transitions.transition_trigger_sql("estimate_version") at CTR-12; DG-ARC-07
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
   WHERE n.key <> ALL (ARRAY['applied_event_ids', 'approval_request_id', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
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


def _create_estimate() -> None:
    ops.create_tenant_table(
        ESTIMATE,
        _uuid("contract_id"),
        _uuid("portfolio_id"),
        _uuid("obligation_id"),
        _named("estimate_kind", "erev.estimate_kind", nullable=False),
        _named("element_code", "erev.code", nullable=False),
        sa.Column("vc_element_type", sa.Text(), nullable=True),
        sa.Column("direction", sa.Text(), nullable=False, server_default=sa.text("'INCREASE'")),
        _named("method", "erev.estimate_method", nullable=False),
        sa.Column(
            "allocation_target", sa.Text(), nullable=False, server_default=sa.text("'CONTRACT'")
        ),
        _named("target_obligation_ids", "uuid[]", nullable=False, default="'{}'::uuid[]"),
        _named("allocation_criteria_evidence", "erev.memo", nullable=True),
        standard_sets=["SC-C"],
        checks=ESTIMATE_CHECKS,
    )
    ops.execute(CODE_INDEX)
    ops.add_tenant_fk(ESTIMATE, "contract_id", "contract")
    ops.add_tenant_fk(ESTIMATE, "obligation_id", "obligation")
    ops.apply_class(ESTIMATE, "IM-A")
    ops.enable_rls(ESTIMATE, "RLS-T")


def _create_estimate_version() -> None:
    ops.create_tenant_table(
        VERSION,
        _uuid("estimate_id", nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        _named("status", "erev.config_status", nullable=False, default="'DRAFT'"),
        sa.Column("effective_date", sa.Date(), nullable=False),
        _named("scenarios", "jsonb", nullable=False, default="'[]'::jsonb"),
        _named("parameters", "jsonb", nullable=False, default="'{}'::jsonb"),
        _named("unconstrained_amount", "erev.money", nullable=True),
        _named("most_conservative_amount", "erev.money", nullable=True),
        _named("constrained_amount", "erev.money", nullable=True),
        _named("rate", "erev.exact", nullable=True),
        _named("expected_total_amount", "erev.money", nullable=True),
        _named("expected_quantity", "erev.exact", nullable=True),
        sa.Column("amortization_months", sa.Integer(), nullable=True),
        _named("currency", "erev.currency_code", nullable=True),
        _named("constraint_checklist", "jsonb", nullable=True),
        _named("rationale", "erev.memo", nullable=False),
        _uuid("judgement_record_id"),
        _named("content_sha256", "erev.sha256", nullable=True),
        _uuid("approval_request_id"),
        _named("applied_event_ids", "uuid[]", nullable=False, default="'{}'::uuid[]"),
        _uuid("supersedes_version_id"),
        standard_sets=["SC-C", "SC-M"],
        checks=VERSION_CHECKS,
        unique=[("ux_estimate_version__no", ["tenant_id", "estimate_id", "version_no"], None)],
        indexes=[("ix_estimate_version__status", ["tenant_id", "status"], None)],
    )
    ops.add_tenant_fk(VERSION, "estimate_id", ESTIMATE)
    ops.add_tenant_fk(VERSION, "judgement_record_id", "judgement_record")
    ops.add_tenant_fk(VERSION, "approval_request_id", "approval_request")
    ops.add_global_fk(VERSION, "currency", "currency", target_column="code")
    ops.add_tenant_fk(VERSION, "supersedes_version_id", VERSION)
    ops.apply_class(VERSION, "IM-S", update_columns=UPDATE_COLUMNS)
    ops.enable_rls(VERSION, "RLS-T")
    ops.create_trigger(VERSION, "transition", TRANSITION_BODY, timing="BEFORE", events="UPDATE")


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("estimate_kind", ESTIMATE_KIND)
    ops.create_enum("estimate_method", ESTIMATE_METHOD)
    _create_estimate()
    _create_estimate_version()
    ops.add_tenant_fk("contract_event", "estimate_version_id", VERSION)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.execute(
        "ALTER TABLE erev.contract_event DROP CONSTRAINT fk_contract_event__estimate_version"
    )
    ops.drop_tenant_table(VERSION)
    ops.drop_tenant_table(ESTIMATE)
    ops.drop_enum("estimate_method")
    ops.drop_enum("estimate_kind")
