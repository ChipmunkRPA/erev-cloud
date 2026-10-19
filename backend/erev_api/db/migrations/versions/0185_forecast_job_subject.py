"""Allow forecast jobs to name their durable forecast_run subject."""

from erev_api.db import migration_ops as ops

revision = "0185"
down_revision = "0184"
branch_labels = None
depends_on = None

PREVIOUS = (
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
    "period_state",
)


def replace_check(values: tuple[str, ...]) -> None:
    listed = ", ".join(f"'{value}'" for value in values)
    ops.execute("ALTER TABLE erev.job DROP CONSTRAINT ck_job__subject_type")
    ops.execute(
        "ALTER TABLE erev.job ADD CONSTRAINT ck_job__subject_type "
        f"CHECK (subject_type IS NULL OR subject_type IN ({listed}))"
    )


def upgrade() -> None:
    replace_check((*PREVIOUS, "forecast_run"))


def downgrade() -> None:
    # Restoring the check deliberately refuses while any forecast jobs remain.
    replace_check(PREVIOUS)
