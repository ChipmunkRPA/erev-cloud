"""Give dated Step 1 submissions their own revalidated approval lifecycle."""

from erev_api.db import migration_ops as ops

revision = "0139"
down_revision = "0138"
branch_labels = None
depends_on = None


def _report_subjects(*, add: bool) -> None:
    # Keep the stored report-filter schema in sync with the runtime catalogue.
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET parameters_schema = jsonb_set("
        "parameters_schema, '{properties,subject_types,items,enum}', "
        "(parameters_schema #> '{properties,subject_types,items,enum}') "
        "|| '[\"STEP1_EVENT\"]'::jsonb) WHERE code = 'approvals_register' AND version = 1"
        if add
        else "UPDATE erev.report_definition SET parameters_schema = jsonb_set("
        "parameters_schema, '{properties,subject_types,items,enum}', "
        "(parameters_schema #> '{properties,subject_types,items,enum}') "
        "- 'STEP1_EVENT') WHERE code = 'approvals_register' AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    ops.add_enum_value("approval_subject_type", "STEP1_EVENT")
    _report_subjects(add=True)


def downgrade() -> None:
    ops.remove_enum_value("approval_subject_type", "STEP1_EVENT")
    _report_subjects(add=False)
