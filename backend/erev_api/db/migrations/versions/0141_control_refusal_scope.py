"""Allow refused period controls to cite the existing period-state row."""

from erev_api.db import migration_ops as ops

revision = "0141"
down_revision = "0140"
branch_labels = None
depends_on = None

BASE = (
    "'CLOSE_RUN','JOURNAL_RUN','IMPORT_UPLOAD','CONTRACT_COMPUTATION','REPORT_RUN',"
    "'AUDIT_CHAIN_VERIFICATION','SYNC_RUN','JOURNAL_BATCH','RECONCILIATION_RUN','PERIOD_LOCK'"
)


def _constraint(values: str) -> None:
    ops.execute(
        "ALTER TABLE erev.control_execution DROP CONSTRAINT ck_control_execution__run_ref_type"
    )
    ops.execute(
        "ALTER TABLE erev.control_execution ADD CONSTRAINT ck_control_execution__run_ref_type "
        f"CHECK (run_ref_type IN ({values}))"
    )


def upgrade() -> None:
    _constraint(BASE + ",'PERIOD_STATE'")


def downgrade() -> None:
    # Validation refuses downgrade if retained observations use the new reference type.
    _constraint(BASE)
