"""SOP-1 control evidence registry: 04 T-PLT-39 ``control_execution`` (IM-A; RLS-T, RLS-TE when
``entity_id`` is not null; PT-N; AUD-FACT) and the deferred foreign key of T-CLS-03
``close_checklist_item.control_execution_id`` (0047: "waits for T-PLT-39").

Revision 0057 on 0056, assigned by the supervisor at merge prep (2026-09-20): 0055 is lane P5
(``engine_release.validation_level``), 0056 lane F-LMG, 0057 this table (drafted as
``make revision MSG=control_execution ITEM=SOP-1``; held under .run/p4/sop1 until the head was
named).

Checks: ``control_id ~ '^CTL-[0-9]{3}$'``; ``run_ref_type`` in the ten T-PLT-39 literals
(04 rev 1.21); counts non-negative. Indexes: ``ix_control_execution__control (tenant_id,
control_id, executed_at)``,
``ix_control_execution__run (tenant_id, run_ref_type, run_ref_id)`` (non-unique: an IM-A re-run
appends a row). Foreign keys: ``engine_release`` (global), ``legal_entity``, ``period``,
``file_object`` (tenant-owned).
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None

TABLE = "control_execution"
RUN_REF_TYPES = (
    "CLOSE_RUN",
    "JOURNAL_RUN",
    "IMPORT_UPLOAD",
    "CONTRACT_COMPUTATION",
    "REPORT_RUN",
    "AUDIT_CHAIN_VERIFICATION",
    "SYNC_RUN",
    "JOURNAL_BATCH",
    "RECONCILIATION_RUN",
    "PERIOD_LOCK",
)


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
    literals = ", ".join(f"'{value}'" for value in RUN_REF_TYPES)
    ops.create_tenant_table(
        TABLE,
        sa.Column("control_id", sa.Text(), nullable=False),
        sa.Column("run_ref_type", sa.Text(), nullable=False),
        _uuid("run_ref_id", nullable=False),
        _uuid("entity_id"),
        _named("book_code", "erev.book_code", nullable=True),
        _uuid("period_id"),
        sa.Column("population_count", sa.BigInteger(), nullable=False),
        sa.Column("exception_count", sa.BigInteger(), nullable=False),
        _named("result", "erev.control_result", nullable=False),
        _named("detail", "jsonb", nullable=False, default="'{}'::jsonb"),
        _uuid("exceptions_file_id"),
        _uuid("engine_release_id", nullable=False),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        standard_sets=[],
        checks=[
            ("ck_control_execution__control_id", "control_id ~ '^CTL-[0-9]{3}$'"),
            ("ck_control_execution__run_ref_type", f"run_ref_type IN ({literals})"),
            ("ck_control_execution__counts", "population_count >= 0 AND exception_count >= 0"),
        ],
        indexes=[
            ("ix_control_execution__control", ["tenant_id", "control_id", "executed_at"], None),
            ("ix_control_execution__run", ["tenant_id", "run_ref_type", "run_ref_id"], None),
        ],
        approval_request_fk=False,
    )
    ops.add_global_fk(TABLE, "engine_release_id", "engine_release")
    ops.add_tenant_fk(TABLE, "entity_id", "legal_entity")
    ops.add_tenant_fk(TABLE, "period_id", "period")
    ops.add_tenant_fk(TABLE, "exceptions_file_id", "file_object")
    ops.apply_class(TABLE, "IM-A")
    ops.enable_rls(TABLE, "RLS-TE", entity_column="entity_id", entity_nullable=True)
    # 0047: the T-CLS-03 placeholder waits for this table.
    ops.add_tenant_fk("close_checklist_item", "control_execution_id", TABLE)


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.close_checklist_item DROP CONSTRAINT IF EXISTS "
        "fk_close_checklist_item__control_execution"
    )
    ops.drop_tenant_table(TABLE)
