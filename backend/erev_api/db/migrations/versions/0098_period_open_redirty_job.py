"""Item CLO-LOCK-OPEN-REDIRTY-1 (supervisor rulings R-101 (a) and R-106 (a) of 2026-09-30; number
assigned by the supervisor): the job that re-marks a period the lock decision opened.

04 ids amended (rev 1.164): E-14 ``job_kind`` gains ``PERIOD_OPEN_REDIRTY`` — the lock decision
that opens the next period (PRD BR-CLS-03) defers one job of that kind for the opened period
state, and the job marks dirty the clean combination groups the opening reaches (05 SCH-06; §5.6
queue ``close``) — and T-PLT-27 ``job.subject_type`` admits ``period_state``, the resource that
job works on (``ck_job__subject_type`` is replaced with the list of revision 0095 plus that
literal): the job's audit facts name its period. No table, column, trigger, function or grant
changes.

The downgrade restores the subject-type check of revision 0095 and rewrites the type without the
label through ``remove_enum_value`` (DG-MIG-06); both fail while a job row still carries the
subject type or the kind. A revision imports nothing of ``erev_api`` beyond the DDL helpers
(DG-MIG-12).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0098"
down_revision = "0091"
branch_labels = None
depends_on = None

ENUM: Final = "job_kind"
VALUE: Final = "PERIOD_OPEN_REDIRTY"
JOB_TABLE: Final = "job"
SUBJECT_CHECK: Final = "ck_job__subject_type"
# 04 T-PLT-27 ``subject_type``: the list of revision 0095, then the literal of rev 1.164.
PREVIOUS_SUBJECT_TYPES: Final = (
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
    "reconciliation",
)
SUBJECT_TYPES: Final = (*PREVIOUS_SUBJECT_TYPES, "period_state")


def _replace_subject_check(subject_types: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{subject}'" for subject in subject_types)
    ops.execute(f"ALTER TABLE erev.{JOB_TABLE} DROP CONSTRAINT {SUBJECT_CHECK}")
    ops.execute(
        f"ALTER TABLE erev.{JOB_TABLE} ADD CONSTRAINT {SUBJECT_CHECK} "
        f"CHECK (subject_type IS NULL OR subject_type IN ({listed}))"
    )


def upgrade() -> None:
    """Add the job kind and its subject type (04 E-14 and T-PLT-27 rev 1.164)."""
    ops.add_enum_value(ENUM, VALUE)
    _replace_subject_check(SUBJECT_TYPES)


def downgrade() -> None:
    """Restore the subject types of revision 0095 and remove the job kind (DG-MIG-04,
    DG-MIG-06)."""
    _replace_subject_check(PREVIOUS_SUBJECT_TYPES)
    ops.remove_enum_value(ENUM, VALUE)
