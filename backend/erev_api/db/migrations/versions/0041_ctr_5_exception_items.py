"""BUILD_SPEC item CTR-5: the shared exception queue.

04 ids created: E-42 ``exception_source``, E-43 ``exception_severity``, E-44 ``exception_status``
and E-106 ``exception_disposition``; T-IMP-05 ``exception_item`` (BS3-D-02; 04 §18 rule 7(b)).

- T-IMP-05 ``exception_item`` (IM-M, DELETE forbidden; RLS-T plus the restrictive policy
  ``entity_id IS NULL OR erev.entity_in_scope(entity_id)``): ``ux_exception_item__no``,
  ``ux_exception_item__open`` (``WHERE status IN ('OPEN','IN_PROGRESS')``),
  ``ix_exception_item__status`` and ``ix_exception_item__contract``; the 04 checks of ``code`` and
  ``priority`` and ``ck_exception_item__waiver`` (the "Required for WAIVED" note); the foreign keys
  to ``contract``, ``obligation``, ``combination_group``, ``legal_entity``, ``period``,
  ``tenant_membership`` and ``approval_request``.

The keys to ``import_upload``, ``import_row``, ``sync_run``, ``source_record``, ``close_run`` and
``journal_run`` are added by the revisions that create those tables (DG-MIG-03; BS3-D-02).
``resolved_by`` is an actor column without a key, as SC-C ``created_by``. No function is added.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

TABLE = "exception_item"
# 04 §3.4 E-42, E-43, E-44 and E-106 (DG-MIG-06).
EXCEPTION_SOURCE = (
    "IMPORT",
    "SYNC",
    "ENGINE",
    "CLOSE",
    "RECONCILIATION",
    "JOURNAL",
    "INTEGRATION",
    "DATA_QUALITY",
    "MIGRATION",
    "ANOMALY",
)
EXCEPTION_SEVERITY = ("BLOCKING", "WARNING", "INFO")
EXCEPTION_STATUS = ("OPEN", "IN_PROGRESS", "RESOLVED", "WAIVED", "DISMISSED")
EXCEPTION_DISPOSITION = ("remediable", "discarded")
FOREIGN_KEYS = (
    ("contract_id", "contract"),
    ("obligation_id", "obligation"),
    ("combination_group_id", "combination_group"),
    ("entity_id", "legal_entity"),
    ("period_id", "period"),
    ("owner_membership_id", "tenant_membership"),
    ("waiver_approval_request_id", "approval_request"),
)


def _uuid(name: str) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), nullable=True)


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


def _create_exception_item() -> None:
    ops.create_tenant_table(
        TABLE,
        _text("exception_no", nullable=False),
        _named("source", "erev.exception_source", nullable=False),
        _text("code", nullable=False),
        _named("severity", "erev.exception_severity", nullable=False),
        _named("disposition", "erev.exception_disposition", nullable=False, default="'remediable'"),
        _named("status", "erev.exception_status", nullable=False, default="'OPEN'"),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default=sa.text("3")),
        _named("title", "erev.label", nullable=False),
        _named("message", "erev.memo", nullable=False),
        _named("suggestion", "erev.memo", nullable=True),
        _text("field"),
        _text("business_key"),
        _named("source_payload", "jsonb", nullable=True),
        _uuid("import_upload_id"),
        _uuid("import_row_id"),
        _uuid("sync_run_id"),
        _uuid("source_record_id"),
        _uuid("contract_id"),
        _uuid("obligation_id"),
        _uuid("combination_group_id"),
        _uuid("entity_id"),
        _uuid("period_id"),
        _uuid("close_run_id"),
        _uuid("journal_run_id"),
        _uuid("owner_membership_id"),
        _text("dedupe_key", nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        _timestamp("last_seen_at", nullable=False, now_default=True),
        _named("resolution", "erev.memo", nullable=True),
        _timestamp("resolved_at"),
        _uuid("resolved_by"),
        _named("resolved_by_kind", "erev.principal_kind", nullable=True),
        _uuid("waiver_approval_request_id"),
        _timestamp("reprocessed_at"),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            ("ck_exception_item__code", "code ~ '^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$'"),
            ("ck_exception_item__priority", "priority BETWEEN 1 AND 5"),
            ("ck_exception_item__occurrence_count", "occurrence_count >= 1"),
            (
                "ck_exception_item__waiver",
                "status <> 'WAIVED' OR waiver_approval_request_id IS NOT NULL",
            ),
        ],
        unique=[
            ("ux_exception_item__no", ["tenant_id", "exception_no"], None),
            (
                "ux_exception_item__open",
                ["tenant_id", "dedupe_key"],
                "status IN ('OPEN','IN_PROGRESS')",
            ),
        ],
        indexes=[
            ("ix_exception_item__status", ["tenant_id", "status", "severity", "created_at"], None),
            ("ix_exception_item__contract", ["tenant_id", "contract_id"], None),
        ],
    )
    for column, target in FOREIGN_KEYS:
        ops.add_tenant_fk(TABLE, column, target)
    ops.apply_class(TABLE, "IM-M")
    ops.enable_rls(TABLE, "RLS-TE", entity_column="entity_id", entity_nullable=True)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("exception_source", EXCEPTION_SOURCE)
    ops.create_enum("exception_severity", EXCEPTION_SEVERITY)
    ops.create_enum("exception_status", EXCEPTION_STATUS)
    ops.create_enum("exception_disposition", EXCEPTION_DISPOSITION)
    _create_exception_item()


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table(TABLE)
    ops.drop_enum("exception_disposition")
    ops.drop_enum("exception_status")
    ops.drop_enum("exception_severity")
    ops.drop_enum("exception_source")
