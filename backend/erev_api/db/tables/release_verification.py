"""Release-validation selection and immutable replay results (revision 0161)."""

from typing import Final

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from erev_api.db.tables import metadata
from erev_api.db.tables.platform import _enum, _sc_c, _sc_m
from erev_api.enums import (
    ComputationTrigger,
    ReleaseValidationStatus,
    ValidationAttemptStatus,
    ValidationGroupOrchestrationState,
    VerificationOutcome,
)

release_validation: Final = sa.Table(
    "release_validation",
    metadata,
    sa.Column("tenant_id", sa.Uuid(), primary_key=True),
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("engine_release_id", sa.Uuid(), nullable=False),
    sa.Column("source_engine_release_id", sa.Uuid(), nullable=True),
    sa.Column("effective_level", sa.Text(), nullable=False),
    sa.Column(
        "status",
        _enum(ReleaseValidationStatus, "release_validation_status"),
        nullable=False,
    ),
    sa.Column("accepted_attempt_id", sa.Uuid(), nullable=True),
    sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
    *_sc_c(),
    *_sc_m(),
)

release_validation_attempt: Final = sa.Table(
    "release_validation_attempt",
    metadata,
    sa.Column("tenant_id", sa.Uuid(), primary_key=True),
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("release_validation_id", sa.Uuid(), nullable=False),
    sa.Column("attempt_no", sa.Integer(), nullable=False),
    sa.Column("seed", sa.BigInteger(), nullable=False),
    sa.Column("population", JSONB(none_as_null=True), nullable=False),
    sa.Column("required_entity_ids", ARRAY(sa.Uuid()), nullable=False),
    sa.Column(
        "status",
        _enum(ValidationAttemptStatus, "validation_attempt_status"),
        nullable=False,
    ),
    sa.Column("dataset_file_id", sa.Uuid(), nullable=True),
    sa.Column("dataset_sha256", sa.CHAR(64), nullable=True),
    sa.Column("report_run_id", sa.Uuid(), nullable=True),
    sa.Column("approval_request_id", sa.Uuid(), nullable=True),
    *_sc_c(),
    *_sc_m(),
)

release_validation_group: Final = sa.Table(
    "release_validation_group",
    metadata,
    sa.Column("tenant_id", sa.Uuid(), primary_key=True),
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("release_validation_attempt_id", sa.Uuid(), nullable=False),
    sa.Column("combination_group_id", sa.Uuid(), nullable=False),
    sa.Column("source_computation_id", sa.Uuid(), nullable=True),
    sa.Column("selection", sa.Text(), nullable=False),
    sa.Column("strata", JSONB(none_as_null=True), nullable=False),
    sa.Column("rank_sha256", sa.CHAR(64), nullable=False),
    sa.Column(
        "orchestration_state",
        _enum(ValidationGroupOrchestrationState, "validation_group_orchestration_state"),
        nullable=False,
    ),
    sa.Column("accepted_verification_id", sa.Uuid(), nullable=True),
    sa.Column("child_job_id", sa.Uuid(), nullable=True),
    *_sc_c(),
    *_sc_m(),
)

computation_verification: Final = sa.Table(
    "computation_verification",
    metadata,
    sa.Column("tenant_id", sa.Uuid(), primary_key=True),
    sa.Column("id", sa.Uuid(), primary_key=True),
    sa.Column("source_computation_id", sa.Uuid(), nullable=True),
    sa.Column("combination_group_id", sa.Uuid(), nullable=False),
    sa.Column(
        "trigger",
        _enum(ComputationTrigger, "computation_trigger"),
        nullable=False,
    ),
    sa.Column("source_engine_release_id", sa.Uuid(), nullable=True),
    sa.Column("source_engine_version", sa.Text(), nullable=True),
    sa.Column("source_codec", JSONB(none_as_null=True), nullable=True),
    sa.Column("process_engine_release_id", sa.Uuid(), nullable=False),
    sa.Column("process_engine_version", sa.Text(), nullable=False),
    sa.Column("engine_executed", sa.Boolean(), nullable=False),
    sa.Column("executed_engine_release_id", sa.Uuid(), nullable=True),
    sa.Column("executed_engine_version", sa.Text(), nullable=True),
    sa.Column("input_transform_id", sa.Text(), nullable=True),
    sa.Column("candidate_input_sha256", sa.CHAR(64), nullable=True),
    sa.Column("input_sha256", sa.CHAR(64), nullable=True),
    sa.Column("input_file_sha256_expected", sa.CHAR(64), nullable=True),
    sa.Column("input_file_sha256_observed", sa.CHAR(64), nullable=True),
    sa.Column("expected_output_sha256", sa.CHAR(64), nullable=True),
    sa.Column("evidence_output_sha256", sa.CHAR(64), nullable=True),
    sa.Column("expected_book_codes", ARRAY(sa.Text()), nullable=True),
    sa.Column("actual_output_sha256", sa.CHAR(64), nullable=True),
    sa.Column("normalised_expected_sha256", sa.CHAR(64), nullable=True),
    sa.Column("normalised_actual_sha256", sa.CHAR(64), nullable=True),
    sa.Column("normalised_input_match", sa.Boolean(), nullable=True),
    sa.Column(
        "outcome",
        _enum(VerificationOutcome, "verification_outcome"),
        nullable=False,
    ),
    sa.Column("reason", sa.Text(), nullable=True),
    sa.Column("difference_summary", JSONB(none_as_null=True), nullable=True),
    sa.Column("difference_file_id", sa.Uuid(), nullable=True),
    sa.Column("release_validation_attempt_id", sa.Uuid(), nullable=True),
    sa.Column("job_id", sa.Uuid(), nullable=False),
    sa.Column("task_id", sa.BigInteger(), nullable=False),
    sa.Column("attempt", sa.Integer(), nullable=False),
    sa.Column("duration_ms", sa.Integer(), nullable=False),
    sa.Column("problem", JSONB(none_as_null=True), nullable=True),
    *_sc_c(),
)
