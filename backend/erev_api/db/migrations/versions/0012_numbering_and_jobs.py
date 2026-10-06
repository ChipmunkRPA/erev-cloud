"""BUILD_SPEC item PLF-9: numbering series, job registry, worker and sweeper.

04 ids created: E-13 ``job_state``; E-14 ``job_kind``; T-PLT-26 ``numbering_series`` (IM-X, RLS-T)
with ``ux_numbering_series__code_scope``; T-PLT-27 ``job`` (IM-S, RLS-T) with ``ix_job__state``,
``ix_job__kind``, ``ix_job__subject`` and the DB-03 trigger ``tg_job__transition``; the schema of
the pinned Procrastinate version in ``public`` with the 04 §14.2 grants (NC-01; DG-MIG-09).
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

# 04 §3.4 E-13 and E-14.
JOB_STATE = ("QUEUED", "RUNNING", "SUCCEEDED", "SUCCEEDED_WITH_EXCEPTIONS", "FAILED", "CANCELLED")
JOB_KIND = (
    "CONTRACT_COMPUTE",
    "IMPORT_VALIDATE",
    "IMPORT_DIFF",
    "IMPORT_COMMIT",
    "CLOSE_RUN",
    "JOURNAL_RUN_CALCULATE",
    "JOURNAL_EXPORT",
    "REPORT_RUN",
    "EVIDENCE_PACK",
    "AUDIT_CHAIN_VERIFY",
    "SSP_CALCULATOR",
    "SYNC_RUN",
    "TENANT_SNAPSHOT",
    "SANDBOX_RESET",
    "MIGRATION_IMPORT",
    "MIGRATION_RECONCILE",
    "REPLAY_VERIFY",
    "POLICY_SIMULATION",
    "FORECAST_RUN",
    "DEAL_PREVIEW",
    "AI_TASK",
    "RETENTION_SWEEP",
    "OUTBOX_RELAY",
    "WEBHOOK_DELIVERY",
    "EMAIL_DELIVERY",
)
# 04 T-PLT-27: the columns erev_app may update.
JOB_UPDATE_COLUMNS = (
    "state",
    "progress_done",
    "progress_total",
    "result",
    "problem",
    "procrastinate_job_id",
    "started_at",
    "finished_at",
    "cancel_requested_at",
    "updated_at",
    "updated_by",
    "updated_by_kind",
    "row_version",
)
SUBJECT_TYPES = (
    "contract",
    "combination_group",
    "modification",
    "estimate_version",
    "import_upload",
    "journal_run",
    "close_run",
    "report_run",
    "evidence_pack",
    "ssp_calculator_run",
    "sync_run",
    "migration_batch",
    "registry_version",
    "ai_proposal",
    "tenant",
)
# DB-03: erev_api.db.transitions.transition_trigger_sql("job") at PLF-9; DG-ARC-07 compares the
# installed function with a fresh rendering.
JOB_TRANSITION_BODY = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['cancel_requested_at', 'finished_at', 'problem', 'procrastinate_job_id', 'progress_done', 'progress_total', 'result', 'row_version', 'started_at', 'state', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.state IS DISTINCT FROM OLD.state
     AND (OLD.state::text || '>' || NEW.state::text) <> ALL (ARRAY['QUEUED>CANCELLED', 'QUEUED>RUNNING', 'RUNNING>CANCELLED', 'RUNNING>FAILED', 'RUNNING>QUEUED', 'RUNNING>SUCCEEDED', 'RUNNING>SUCCEEDED_WITH_EXCEPTIONS']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: state of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.state, NEW.state);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("job_state", JOB_STATE)
    ops.create_enum("job_kind", JOB_KIND)

    ops.create_tenant_table(
        "numbering_series",
        sa.Column("series_code", sa.Text(), nullable=False),
        sa.Column("scope_key", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("prefix", sa.Text(), nullable=False),
        sa.Column("next_value", sa.BigInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("padding", sa.Integer(), nullable=False, server_default=sa.text("6")),
        sa.Column("is_gapless", sa.Boolean(), nullable=False),
        standard_sets=["SC-M"],
        checks=[("ck_numbering_series__next_value", "next_value >= 1")],
        unique=[
            (
                "ux_numbering_series__code_scope",
                ["tenant_id", "series_code", "scope_key"],
                None,
            )
        ],
    )
    ops.apply_class("numbering_series", "IM-X")
    ops.enable_rls("numbering_series", "RLS-T")

    jsonb = ops.NamedType("jsonb")
    subject_types = ", ".join(f"'{subject}'" for subject in SUBJECT_TYPES)
    ops.create_tenant_table(
        "job",
        sa.Column("kind", ops.NamedType("erev.job_kind"), nullable=False),
        sa.Column(
            "state",
            ops.NamedType("erev.job_state"),
            nullable=False,
            server_default=sa.text("'QUEUED'"),
        ),
        sa.Column("params", jsonb, nullable=False),
        sa.Column("queue", sa.Text(), nullable=False, server_default=sa.text("'default'")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("progress_done", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("progress_total", sa.BigInteger(), nullable=True),
        sa.Column("result", jsonb, nullable=True),
        sa.Column("problem", jsonb, nullable=True),
        sa.Column("procrastinate_job_id", sa.BigInteger(), nullable=True),
        sa.Column("parent_job_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subject_type", sa.Text(), nullable=True),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            ("ck_job__params", "jsonb_typeof(params) = 'object'"),
            ("ck_job__subject", "(subject_type IS NULL) = (subject_id IS NULL)"),
            ("ck_job__subject_type", f"subject_type IS NULL OR subject_type IN ({subject_types})"),
        ],
        indexes=[
            ("ix_job__state", ["tenant_id", "state", "created_at"], None),
            ("ix_job__kind", ["tenant_id", "kind", "created_at"], None),
            ("ix_job__subject", ["tenant_id", "subject_type", "subject_id", "created_at"], None),
        ],
    )
    ops.add_tenant_fk("job", "parent_job_id", "job")
    ops.apply_class("job", "IM-S", update_columns=JOB_UPDATE_COLUMNS)
    ops.enable_rls("job", "RLS-T")
    ops.create_trigger("job", "transition", JOB_TRANSITION_BODY, timing="BEFORE", events="UPDATE")

    ops.install_procrastinate_schema()


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_procrastinate_schema()
    ops.drop_tenant_table("job")
    ops.drop_tenant_table("numbering_series")
    ops.drop_enum("job_kind")
    ops.drop_enum("job_state")
