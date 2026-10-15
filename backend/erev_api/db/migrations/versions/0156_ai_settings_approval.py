"""Separate administrator AI settings approvals from accounting configuration requests."""

from erev_api.db import migration_ops as ops

revision = "0156"
down_revision = "0155"
branch_labels = None
depends_on = None


def _catalogues(*, add: bool) -> None:
    ops.execute("ALTER TABLE erev.permission DISABLE TRIGGER tg_permission__immutable")
    ops.execute(
        "UPDATE erev.permission SET is_approval = true, "
        "description = 'Manage tenant settings and approve AI settings' "
        "WHERE code = 'settings.manage'"
        if add
        else "UPDATE erev.permission SET is_approval = false, "
        "description = 'Manage tenant settings' WHERE code = 'settings.manage'"
    )
    ops.execute("ALTER TABLE erev.permission ENABLE TRIGGER tg_permission__immutable")
    ops.execute(
        "ALTER TABLE erev.report_definition DISABLE TRIGGER tg_report_definition__immutable"
    )
    ops.execute(
        "UPDATE erev.report_definition SET parameters_schema = jsonb_set("
        "parameters_schema, '{properties,subject_types,items,enum}', "
        "replace((parameters_schema #> '{properties,subject_types,items,enum}')::text, "
        '\'"REGISTRY_VERSION"\', \'"REGISTRY_VERSION", "AI_SETTINGS_VERSION"\')::jsonb) '
        "WHERE code IN ('approvals_register', 'config_change_register') AND version = 1"
        if add
        else "UPDATE erev.report_definition SET parameters_schema = jsonb_set("
        "parameters_schema, '{properties,subject_types,items,enum}', "
        "(parameters_schema #> '{properties,subject_types,items,enum}') - 'AI_SETTINGS_VERSION') "
        "WHERE code IN ('approvals_register', 'config_change_register') AND version = 1"
    )
    ops.execute("ALTER TABLE erev.report_definition ENABLE TRIGGER tg_report_definition__immutable")


def upgrade() -> None:
    ops.add_enum_value("approval_subject_type", "AI_SETTINGS_VERSION", after="REGISTRY_VERSION")
    _catalogues(add=True)


def downgrade() -> None:
    # Refuses removal while retained approval evidence still uses this subject.
    ops.remove_enum_value("approval_subject_type", "AI_SETTINGS_VERSION")
    _catalogues(add=False)
