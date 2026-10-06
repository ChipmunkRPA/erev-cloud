"""BUILD_SPEC item RFD-15: historical SSP calculator.

04 ids created: E-67 ``run_status``; T-REF-32 ``ssp_calculator_run`` (IM-S, RLS-T) with the checks
``ck_ssp_calculator_run__parameters`` and ``ck_ssp_calculator_run__observation_count``, the foreign
keys ``result_file_id`` → ``file_object``, ``draft_ssp_book_version_id`` → ``ssp_book_version``
and ``job_id`` → ``job``, and the DB-03 trigger ``tg_ssp_calculator_run__transition`` rendered from
``erev_api.db.transitions``; T-REF-33 ``ssp_calculator_result`` (IM-A, RLS-T) with
``ix_ssp_calculator_result__run``, the checks ``ck_ssp_calculator_result__counts``,
``__dimension_key`` and ``__histogram``, and the foreign keys to the run, ``product`` and
``currency``; T-REF-34 ``ssp_calculator_exclusion`` (IM-A, RLS-T) with the 04 key
``ux_ssp_calculator_exclusion`` named ``ux_ssp_calculator_exclusion__source_ref`` (NC-16), the 04
check named ``ck_ssp_calculator_exclusion__source_ref_type`` and the foreign key to the run. The
checks and foreign keys 04 does not name are L2-1-Q-54. The foreign key
``ssp_book_version.ssp_calculator_run_id`` → ``ssp_calculator_run`` of T-REF-29 is added here,
because this revision creates the run table (DG-MIG-03). One function is added (the DB-03 trigger).
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None

# 04 §3.4 E-67 (DG-MIG-06).
RUN_STATUS = ("QUEUED", "RUNNING", "SUCCEEDED", "FAILED")
# 04 T-REF-32 IM-S: the columns erev_app may update.
RUN_UPDATE_COLUMNS = (
    "status",
    "observation_count",
    "result_file_id",
    "draft_ssp_book_version_id",
    "started_at",
    "finished_at",
)
# DB-03: erev_api.db.transitions.transition_trigger_sql("ssp_calculator_run") at RFD-15; DG-ARC-07
# compares the installed function with a fresh rendering.
RUN_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['draft_ssp_book_version_id', 'finished_at', 'observation_count', 'result_file_id', 'started_at', 'status']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.draft_ssp_book_version_id IS NOT NULL AND NEW.draft_ssp_book_version_id IS DISTINCT FROM OLD.draft_ssp_book_version_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: draft_ssp_book_version_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.finished_at IS NOT NULL AND NEW.finished_at IS DISTINCT FROM OLD.finished_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: finished_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.started_at IS NOT NULL AND NEW.started_at IS DISTINCT FROM OLD.started_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: started_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['QUEUED>FAILED', 'QUEUED>RUNNING', 'RUNNING>FAILED', 'RUNNING>SUCCEEDED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def _exact(name: str) -> sa.Column[Any]:
    return sa.Column(name, ops.NamedType("erev.exact"), nullable=False)


def _timestamp(name: str) -> sa.Column[Any]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=True)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("run_status", RUN_STATUS)

    ops.create_tenant_table(
        "ssp_calculator_run",
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("parameters", ops.NamedType("jsonb"), nullable=False),
        sa.Column(
            "status",
            ops.NamedType("erev.run_status"),
            nullable=False,
            server_default=sa.text("'QUEUED'"),
        ),
        sa.Column("observation_count", sa.Integer(), nullable=True),
        sa.Column("result_file_id", sa.Uuid(), nullable=True),
        sa.Column("draft_ssp_book_version_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        _timestamp("started_at"),
        _timestamp("finished_at"),
        standard_sets=["SC-C"],
        checks=[
            ("ck_ssp_calculator_run__parameters", "jsonb_typeof(parameters) = 'object'"),
            (
                "ck_ssp_calculator_run__observation_count",
                "observation_count IS NULL OR observation_count >= 0",
            ),
        ],
    )
    ops.add_tenant_fk("ssp_calculator_run", "result_file_id", "file_object")
    ops.add_tenant_fk("ssp_calculator_run", "draft_ssp_book_version_id", "ssp_book_version")
    ops.add_tenant_fk("ssp_calculator_run", "job_id", "job")
    ops.apply_class("ssp_calculator_run", "IM-S", update_columns=RUN_UPDATE_COLUMNS)
    ops.enable_rls("ssp_calculator_run", "RLS-T")
    ops.create_trigger(
        "ssp_calculator_run",
        "transition",
        RUN_TRANSITION_BODY,
        timing="BEFORE",
        events="UPDATE",
    )

    ops.create_tenant_table(
        "ssp_calculator_result",
        sa.Column("ssp_calculator_run_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("stratification", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "dimension_key",
            ops.NamedType("jsonb"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("currency", ops.NamedType("erev.currency_code"), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("excluded_count", sa.Integer(), nullable=False),
        _exact("median_unit_price"),
        _exact("mean_unit_price"),
        _exact("p10_unit_price"),
        _exact("p25_unit_price"),
        _exact("p75_unit_price"),
        _exact("p90_unit_price"),
        _exact("band_ratio"),
        _exact("compliance_ratio"),
        sa.Column("inside_count", sa.Integer(), nullable=False),
        _exact("proposed_low"),
        _exact("proposed_mid"),
        _exact("proposed_high"),
        sa.Column("histogram", ops.NamedType("jsonb"), nullable=False),
        checks=[
            (
                "ck_ssp_calculator_result__counts",
                "observation_count >= 1 AND excluded_count >= 0 AND inside_count >= 0 "
                "AND inside_count <= observation_count",
            ),
            ("ck_ssp_calculator_result__dimension_key", "jsonb_typeof(dimension_key) = 'object'"),
            ("ck_ssp_calculator_result__histogram", "jsonb_typeof(histogram) = 'array'"),
        ],
        indexes=[("ix_ssp_calculator_result__run", ["tenant_id", "ssp_calculator_run_id"], None)],
    )
    ops.add_tenant_fk("ssp_calculator_result", "ssp_calculator_run_id", "ssp_calculator_run")
    ops.add_tenant_fk("ssp_calculator_result", "product_id", "product")
    ops.add_global_fk("ssp_calculator_result", "currency", "currency", target_column="code")
    ops.apply_class("ssp_calculator_result", "IM-A")
    ops.enable_rls("ssp_calculator_result", "RLS-T")

    ops.create_tenant_table(
        "ssp_calculator_exclusion",
        sa.Column("ssp_calculator_run_id", sa.Uuid(), nullable=False),
        sa.Column("source_ref_type", sa.Text(), nullable=False),
        sa.Column("source_ref_id", sa.Uuid(), nullable=False),
        sa.Column("reason", ops.NamedType("erev.memo"), nullable=False),
        standard_sets=["SC-C"],
        checks=[
            (
                "ck_ssp_calculator_exclusion__source_ref_type",
                "source_ref_type IN ('source_order_line', 'obligation_version')",
            )
        ],
        unique=[
            (
                "ux_ssp_calculator_exclusion__source_ref",
                ["tenant_id", "ssp_calculator_run_id", "source_ref_type", "source_ref_id"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("ssp_calculator_exclusion", "ssp_calculator_run_id", "ssp_calculator_run")
    ops.apply_class("ssp_calculator_exclusion", "IM-A")
    ops.enable_rls("ssp_calculator_exclusion", "RLS-T")

    ops.add_tenant_fk("ssp_book_version", "ssp_calculator_run_id", "ssp_calculator_run")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.execute(
        "ALTER TABLE erev.ssp_book_version DROP CONSTRAINT fk_ssp_book_version__ssp_calculator_run"
    )
    ops.drop_tenant_table("ssp_calculator_exclusion")
    ops.drop_tenant_table("ssp_calculator_result")
    ops.drop_tenant_table("ssp_calculator_run")
    ops.drop_enum("run_status")
