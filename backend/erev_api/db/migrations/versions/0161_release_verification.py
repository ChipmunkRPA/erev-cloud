"""Frozen release-validation selections and immutable replay execution results."""

import sqlalchemy as sa
from erev_api.db import migration_ops as ops
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "0161"
down_revision = "0160"
branch_labels = None
depends_on = None

RELEASE_VALIDATION_TRANSITION = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['accepted_attempt_id', 'enabled_at', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.accepted_attempt_id IS NOT NULL AND NEW.accepted_attempt_id IS DISTINCT FROM OLD.accepted_attempt_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: accepted_attempt_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.enabled_at IS NOT NULL AND NEW.enabled_at IS DISTINCT FROM OLD.enabled_at THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: enabled_at of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['INCOMPLETE>RUNNING', 'PENDING>RUNNING', 'PENDING_APPROVAL>APPROVED', 'PENDING_APPROVAL>REJECTED', 'RUNNING>FAILED', 'RUNNING>INCOMPLETE', 'RUNNING>PASSED', 'RUNNING>PENDING_APPROVAL']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

RELEASE_VALIDATION_ATTEMPT_TRANSITION = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['approval_request_id', 'dataset_file_id', 'dataset_sha256', 'report_run_id', 'row_version', 'status', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.approval_request_id IS NOT NULL AND NEW.approval_request_id IS DISTINCT FROM OLD.approval_request_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: approval_request_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.dataset_file_id IS NOT NULL AND NEW.dataset_file_id IS DISTINCT FROM OLD.dataset_file_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: dataset_file_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.dataset_sha256 IS NOT NULL AND NEW.dataset_sha256 IS DISTINCT FROM OLD.dataset_sha256 THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: dataset_sha256 of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.report_run_id IS NOT NULL AND NEW.report_run_id IS DISTINCT FROM OLD.report_run_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: report_run_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.status IS DISTINCT FROM OLD.status
     AND (OLD.status::text || '>' || NEW.status::text) <> ALL (ARRAY['COMPLETE>SUPERSEDED', 'INCOMPLETE>SUPERSEDED', 'RUNNING>COMPLETE', 'RUNNING>INCOMPLETE', 'RUNNING>SUPERSEDED', 'SELECTED>RUNNING', 'SELECTED>SUPERSEDED']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: status of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501

RELEASE_VALIDATION_GROUP_TRANSITION = """
DECLARE
  old_row jsonb := to_jsonb(OLD);
  new_row jsonb := to_jsonb(NEW);
  changed text;
BEGIN
  SELECT string_agg(n.key, ', ' ORDER BY n.key) INTO changed
    FROM jsonb_each(new_row) n
   WHERE n.key <> ALL (ARRAY['accepted_verification_id', 'child_job_id', 'orchestration_state', 'row_version', 'updated_at', 'updated_by', 'updated_by_kind']::text[])
     AND n.value IS DISTINCT FROM old_row -> n.key;
  IF changed IS NOT NULL THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: columns %s of %I.%I cannot change',
                       changed, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF OLD.accepted_verification_id IS NOT NULL AND NEW.accepted_verification_id IS DISTINCT FROM OLD.accepted_verification_id THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: accepted_verification_id of %I.%I is already set',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  IF NEW.orchestration_state IS DISTINCT FROM OLD.orchestration_state
     AND (OLD.orchestration_state::text || '>' || NEW.orchestration_state::text) <> ALL (ARRAY['PENDING>CANCELLED', 'PENDING>FAILED_EXHAUSTED', 'PENDING>RUNNING', 'RETRYABLE>CANCELLED', 'RETRYABLE>FAILED_EXHAUSTED', 'RETRYABLE>PENDING', 'RETRYABLE>RUNNING', 'RUNNING>CANCELLED', 'RUNNING>COMPLETE', 'RUNNING>FAILED_EXHAUSTED', 'RUNNING>RETRYABLE']::text[]) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-TRN-001: orchestration_state of %I.%I cannot change from %s to %s',
                       TG_TABLE_SCHEMA, TG_TABLE_NAME, OLD.orchestration_state, NEW.orchestration_state);
  END IF;
  RETURN NEW;
END
"""  # noqa: E501


def upgrade() -> None:
    ops.create_tenant_table(
        "release_validation",
        sa.Column("engine_release_id", sa.Uuid(), nullable=False),
        sa.Column("source_engine_release_id", sa.Uuid(), nullable=True),
        sa.Column("effective_level", sa.Text(), nullable=False),
        sa.Column("status", ops.NamedType("erev.release_validation_status"), nullable=False),
        sa.Column("accepted_attempt_id", sa.Uuid(), nullable=True),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            (
                "ck_release_validation__level",
                "effective_level IN ('PATCH','MINOR','MAJOR','BASELINE','BOOTSTRAP')",
            ),
            (
                "ck_release_validation__enabled",
                "(enabled_at IS NOT NULL) = (status IN ('PASSED','APPROVED'))",
            ),
        ],
        unique=[("ux_release_validation__release", ["tenant_id", "engine_release_id"], None)],
    )
    ops.create_tenant_table(
        "release_validation_attempt",
        sa.Column("release_validation_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("population", JSONB(), nullable=False),
        sa.Column("required_entity_ids", ARRAY(sa.Uuid()), nullable=False),
        sa.Column("status", ops.NamedType("erev.validation_attempt_status"), nullable=False),
        sa.Column("dataset_file_id", sa.Uuid(), nullable=True),
        sa.Column("dataset_sha256", ops.NamedType("erev.sha256"), nullable=True),
        sa.Column("report_run_id", sa.Uuid(), nullable=True),
        sa.Column("approval_request_id", sa.Uuid(), nullable=True),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            ("ck_release_validation_attempt__attempt", "attempt_no >= 1"),
            (
                "ck_release_validation_attempt__dataset",
                "(dataset_file_id IS NULL) = (dataset_sha256 IS NULL)",
            ),
            ("ck_release_validation_attempt__population", "jsonb_typeof(population) = 'object'"),
        ],
        unique=[
            (
                "ux_release_validation_attempt__attempt",
                ["tenant_id", "release_validation_id", "attempt_no"],
                None,
            )
        ],
    )
    ops.create_tenant_table(
        "release_validation_group",
        sa.Column("release_validation_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("combination_group_id", sa.Uuid(), nullable=False),
        sa.Column("source_computation_id", sa.Uuid(), nullable=True),
        sa.Column("selection", sa.Text(), nullable=False),
        sa.Column("strata", JSONB(), nullable=False),
        sa.Column("rank_sha256", ops.NamedType("erev.sha256"), nullable=False),
        sa.Column(
            "orchestration_state",
            ops.NamedType("erev.validation_group_orchestration_state"),
            nullable=False,
        ),
        sa.Column("accepted_verification_id", sa.Uuid(), nullable=True),
        sa.Column("child_job_id", sa.Uuid(), nullable=True),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            ("ck_release_validation_group__selection", "selection IN ('OPEN_ACTIVITY','SAMPLED')"),
            ("ck_release_validation_group__strata", "jsonb_typeof(strata) = 'array'"),
        ],
        unique=[
            (
                "ux_release_validation_group__group",
                ["tenant_id", "release_validation_attempt_id", "combination_group_id"],
                None,
            )
        ],
    )
    ops.create_tenant_table(
        "computation_verification",
        sa.Column("source_computation_id", sa.Uuid(), nullable=True),
        sa.Column("combination_group_id", sa.Uuid(), nullable=False),
        sa.Column("trigger", ops.NamedType("erev.computation_trigger"), nullable=False),
        sa.Column("source_engine_release_id", sa.Uuid(), nullable=True),
        sa.Column("source_engine_version", sa.Text(), nullable=True),
        sa.Column("source_codec", JSONB(), nullable=True),
        sa.Column("process_engine_release_id", sa.Uuid(), nullable=False),
        sa.Column("process_engine_version", sa.Text(), nullable=False),
        sa.Column("engine_executed", sa.Boolean(), nullable=False),
        sa.Column("executed_engine_release_id", sa.Uuid(), nullable=True),
        sa.Column("executed_engine_version", sa.Text(), nullable=True),
        sa.Column("input_transform_id", sa.Text(), nullable=True),
        sa.Column("candidate_input_sha256", ops.NamedType("erev.sha256"), nullable=True),
        sa.Column("input_sha256", ops.NamedType("erev.sha256"), nullable=True),
        sa.Column("input_file_sha256_expected", ops.NamedType("erev.sha256"), nullable=True),
        sa.Column("input_file_sha256_observed", ops.NamedType("erev.sha256"), nullable=True),
        sa.Column("expected_output_sha256", ops.NamedType("erev.sha256"), nullable=True),
        sa.Column("evidence_output_sha256", ops.NamedType("erev.sha256"), nullable=True),
        sa.Column("expected_book_codes", ARRAY(sa.Text()), nullable=True),
        sa.Column("actual_output_sha256", ops.NamedType("erev.sha256"), nullable=True),
        sa.Column("normalised_expected_sha256", ops.NamedType("erev.sha256"), nullable=True),
        sa.Column("normalised_actual_sha256", ops.NamedType("erev.sha256"), nullable=True),
        sa.Column("normalised_input_match", sa.Boolean(), nullable=True),
        sa.Column("outcome", ops.NamedType("erev.verification_outcome"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("difference_summary", JSONB(), nullable=True),
        sa.Column("difference_file_id", sa.Uuid(), nullable=True),
        sa.Column("release_validation_attempt_id", sa.Uuid(), nullable=True),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("problem", JSONB(), nullable=True),
        standard_sets=["SC-C"],
        checks=[
            (
                "ck_computation_verification__trigger",
                "trigger IN ('REPLAY_VERIFY','UPGRADE_VALIDATE')",
            ),
            (
                "ck_computation_verification__executed_identity",
                "(engine_executed AND executed_engine_release_id IS NOT NULL AND "
                "executed_engine_version IS NOT NULL) OR (NOT engine_executed AND "
                "executed_engine_release_id IS NULL AND executed_engine_version IS "
                "NULL)",
            ),
            (
                "ck_computation_verification__no_output_without_execution",
                "engine_executed OR actual_output_sha256 IS NULL",
            ),
            (
                "ck_computation_verification__integrity_source",
                "NOT (engine_executed AND trigger = 'REPLAY_VERIFY') OR "
                "(source_computation_id IS NOT NULL AND source_engine_version IS "
                "NOT NULL AND executed_engine_version = source_engine_version)",
            ),
            (
                "ck_computation_verification__candidate_release",
                "NOT (engine_executed AND trigger = 'UPGRADE_VALIDATE') OR "
                "executed_engine_release_id = process_engine_release_id",
            ),
            ("ck_computation_verification__reason", "outcome = 'MATCH' OR reason IS NOT NULL"),
            (
                "ck_computation_verification__source",
                "(source_computation_id IS NULL) = (outcome = 'NO_SOURCE')",
            ),
            (
                "ck_computation_verification__execution",
                "task_id > 0 AND attempt > 0 AND duration_ms >= 0",
            ),
        ],
        unique=[
            (
                "ux_computation_verification__token",
                [
                    "tenant_id",
                    "release_validation_attempt_id",
                    "combination_group_id",
                    "job_id",
                    "task_id",
                ],
                "release_validation_attempt_id IS NOT NULL",
            )
        ],
    )
    ops.add_tenant_fk("release_validation", "accepted_attempt_id", "release_validation_attempt")
    ops.add_tenant_fk("release_validation_attempt", "release_validation_id", "release_validation")
    ops.add_tenant_fk("release_validation_attempt", "dataset_file_id", "file_object")
    ops.add_tenant_fk("release_validation_attempt", "report_run_id", "report_run")
    ops.add_tenant_fk("release_validation_attempt", "approval_request_id", "approval_request")
    ops.add_tenant_fk(
        "release_validation_group", "release_validation_attempt_id", "release_validation_attempt"
    )
    ops.add_tenant_fk("release_validation_group", "combination_group_id", "combination_group")
    ops.add_tenant_fk("release_validation_group", "source_computation_id", "contract_computation")
    ops.add_tenant_fk(
        "release_validation_group", "accepted_verification_id", "computation_verification"
    )
    ops.add_tenant_fk("release_validation_group", "child_job_id", "job")
    ops.add_tenant_fk("computation_verification", "source_computation_id", "contract_computation")
    ops.add_tenant_fk("computation_verification", "combination_group_id", "combination_group")
    ops.add_tenant_fk("computation_verification", "difference_file_id", "file_object")
    ops.add_tenant_fk(
        "computation_verification", "release_validation_attempt_id", "release_validation_attempt"
    )
    ops.add_tenant_fk("computation_verification", "job_id", "job")
    ops.add_global_fk("release_validation", "engine_release_id", "engine_release")
    ops.add_global_fk("release_validation", "source_engine_release_id", "engine_release")
    ops.add_global_fk("computation_verification", "source_engine_release_id", "engine_release")
    ops.add_global_fk("computation_verification", "process_engine_release_id", "engine_release")
    ops.add_global_fk("computation_verification", "executed_engine_release_id", "engine_release")
    ops.apply_class(
        "release_validation",
        "IM-S",
        update_columns=[
            "accepted_attempt_id",
            "enabled_at",
            "row_version",
            "status",
            "updated_at",
            "updated_by",
            "updated_by_kind",
        ],
    )
    ops.create_trigger(
        "release_validation",
        "transition",
        RELEASE_VALIDATION_TRANSITION,
        timing="BEFORE",
        events="UPDATE",
    )
    ops.enable_rls("release_validation", "RLS-T")
    ops.apply_class(
        "release_validation_attempt",
        "IM-S",
        update_columns=[
            "approval_request_id",
            "dataset_file_id",
            "dataset_sha256",
            "report_run_id",
            "row_version",
            "status",
            "updated_at",
            "updated_by",
            "updated_by_kind",
        ],
    )
    ops.create_trigger(
        "release_validation_attempt",
        "transition",
        RELEASE_VALIDATION_ATTEMPT_TRANSITION,
        timing="BEFORE",
        events="UPDATE",
    )
    ops.enable_rls("release_validation_attempt", "RLS-T")
    ops.apply_class(
        "release_validation_group",
        "IM-S",
        update_columns=[
            "accepted_verification_id",
            "child_job_id",
            "orchestration_state",
            "row_version",
            "updated_at",
            "updated_by",
            "updated_by_kind",
        ],
    )
    ops.create_trigger(
        "release_validation_group",
        "transition",
        RELEASE_VALIDATION_GROUP_TRANSITION,
        timing="BEFORE",
        events="UPDATE",
    )
    ops.enable_rls("release_validation_group", "RLS-T")
    ops.apply_class("computation_verification", "IM-A")
    ops.enable_rls("computation_verification", "RLS-T")
    ops.create_indexes(
        "computation_verification",
        [
            (
                "ix_computation_verification__source",
                ["tenant_id", "source_computation_id", "created_at"],
                None,
            )
        ],
        unique=False,
    )

    ops.execute(
        "ALTER TABLE erev.release_validation ADD CONSTRAINT "
        "ck_release_validation__accepted CHECK (enabled_at IS NULL OR "
        "effective_level NOT IN ('MINOR','MAJOR') OR accepted_attempt_id IS NOT NULL)"
    )
    ops.create_trigger(
        "release_validation",
        "accepted_owner",
        """
    BEGIN
        IF NEW.accepted_attempt_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM erev.release_validation_attempt a
            WHERE a.tenant_id = NEW.tenant_id AND a.id = NEW.accepted_attempt_id
              AND a.release_validation_id = NEW.id AND a.status = 'COMPLETE'
        ) THEN
            RAISE EXCEPTION 'Accepted attempt is incomplete or belongs to another validation'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END;
    """,
        timing="BEFORE",
        events="INSERT OR UPDATE",
    )
    ops.create_trigger(
        "release_validation_group",
        "accepted_owner",
        """
    BEGIN
        IF NEW.accepted_verification_id IS NOT NULL AND (
            NEW.orchestration_state <> 'COMPLETE' OR NOT EXISTS (
                SELECT 1 FROM erev.computation_verification v
                WHERE v.tenant_id = NEW.tenant_id AND v.id = NEW.accepted_verification_id
                  AND v.release_validation_attempt_id = NEW.release_validation_attempt_id
                  AND v.combination_group_id = NEW.combination_group_id
                  AND v.source_computation_id IS NOT DISTINCT FROM NEW.source_computation_id
                  AND v.outcome <> 'ERROR'
            )
        ) THEN
            RAISE EXCEPTION 'Accepted verification must belong to this selection and not be ERROR'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END;
    """,
        timing="BEFORE",
        events="INSERT OR UPDATE",
    )


def downgrade() -> None:
    ops.execute(
        "ALTER TABLE erev.release_validation ADD CONSTRAINT "
        "ck_release_validation__empty CHECK (false) NOT VALID"
    )
    ops.execute(
        "ALTER TABLE erev.release_validation VALIDATE CONSTRAINT ck_release_validation__empty"
    )
    ops.execute(
        "ALTER TABLE erev.release_validation_attempt ADD CONSTRAINT "
        "ck_release_validation_attempt__empty CHECK (false) NOT VALID"
    )
    ops.execute(
        "ALTER TABLE erev.release_validation_attempt VALIDATE CONSTRAINT "
        "ck_release_validation_attempt__empty"
    )
    ops.execute(
        "ALTER TABLE erev.release_validation_group ADD CONSTRAINT "
        "ck_release_validation_group__empty CHECK (false) NOT VALID"
    )
    ops.execute(
        "ALTER TABLE erev.release_validation_group VALIDATE CONSTRAINT "
        "ck_release_validation_group__empty"
    )
    ops.execute(
        "ALTER TABLE erev.computation_verification ADD CONSTRAINT "
        "ck_computation_verification__empty CHECK (false) NOT VALID"
    )
    ops.execute(
        "ALTER TABLE erev.computation_verification VALIDATE CONSTRAINT "
        "ck_computation_verification__empty"
    )
    ops.execute(
        "ALTER TABLE erev.release_validation DROP CONSTRAINT "
        "fk_release_validation__accepted_attempt"
    )
    ops.execute(
        "ALTER TABLE erev.release_validation_group DROP CONSTRAINT "
        "fk_release_validation_group__accepted_verification"
    )
    ops.drop_tenant_table("computation_verification")
    ops.drop_tenant_table("release_validation_group")
    ops.drop_tenant_table("release_validation_attempt")
    ops.drop_tenant_table("release_validation")
