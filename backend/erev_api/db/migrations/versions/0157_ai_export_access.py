"""Retain immutable requester authorization for queued AI call exports."""

from erev_api.db import migration_ops as ops

revision = "0157"
down_revision = "0156"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute("ALTER TABLE erev.report_run ADD COLUMN ai_export_access jsonb")
    # IS TRUE refuses SQL NULL from missing JSON members, as well as invalid values.
    ops.execute("""
        ALTER TABLE erev.report_run ADD CONSTRAINT ck_report_run__ai_export_access CHECK (
            (report_code <> 'ai_call_log_export' OR ai_export_access IS NOT NULL)
            AND (ai_export_access IS NULL OR (
                jsonb_typeof(ai_export_access) = 'object'
                AND ai_export_access - ARRAY[
                    'version', 'tenant_id', 'actor_id', 'actor_kind', 'scope'
                ] = '{}'::jsonb
                AND ai_export_access -> 'version' = '1'::jsonb
                AND ai_export_access ->> 'tenant_id' = tenant_id::text
                AND ai_export_access ->> 'actor_id' = created_by::text
                AND ai_export_access ->> 'actor_kind' = created_by_kind::text
                AND ai_export_access ->> 'actor_kind' IN ('USER', 'API_CLIENT')
                AND ai_export_access ->> 'scope' IN ('OWN', 'TENANT')
            ) IS TRUE)
        )
    """)
    ops.create_indexes(
        "report_run",
        [
            (
                "ix_report_run__ai_export_job",
                ["tenant_id", "job_id"],
                "ai_export_access IS NOT NULL OR report_code = 'ai_call_log_export'",
            )
        ],
        unique=False,
    )
    ops.create_trigger(
        "report_run",
        "ai_export_access",
        """
        BEGIN
            IF NEW.ai_export_access IS DISTINCT FROM OLD.ai_export_access THEN
                RAISE EXCEPTION 'Call export requester binding is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        """,
        timing="BEFORE",
        events="UPDATE",
    )


def downgrade() -> None:
    # Losing retained ownership would make these artifacts ordinary entity-scoped reports.
    ops.execute("""
        ALTER TABLE erev.report_run ADD CONSTRAINT ck_report_run__0157_empty
        CHECK (ai_export_access IS NULL AND report_code <> 'ai_call_log_export') NOT VALID
    """)
    ops.execute("ALTER TABLE erev.report_run VALIDATE CONSTRAINT ck_report_run__0157_empty")
    ops.execute("DROP INDEX erev.ix_report_run__ai_export_job")
    ops.execute("DROP TRIGGER tg_report_run__ai_export_access ON erev.report_run")
    ops.execute("DROP FUNCTION erev.tg_report_run__ai_export_access()")
    ops.execute("""
        ALTER TABLE erev.report_run DROP CONSTRAINT ck_report_run__0157_empty,
        DROP CONSTRAINT ck_report_run__ai_export_access, DROP COLUMN ai_export_access
    """)
