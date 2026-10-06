"""BUILD_SPEC item PLF-12: rule sets, approval routing and auto-approval.

04 ids created: E-55 ``rule_set_kind``; the DB-04 function ``erev.tg_config_child()``; T-REF-24
``rule_set`` (IM-M, RLS-T) with ``ux_rule_set__code``; T-REF-25 ``rule_set_version`` (IM-P, SC-V,
RLS-T) with ``ux_rule_set_version__no`` and the DB-04 trigger
``tg_rule_set_version__config_version`` (scope key ``rule_set_id``); T-REF-26 ``rule`` (IM-P
child, RLS-T) with ``ux_rule__key`` and ``tg_rule__config_child``; T-REF-27 ``rule_test_case``
(IM-P child, RLS-T) with ``ix_rule_test_case__subject`` and
``tg_rule_test_case__config_child``; the foreign keys
``approval_request.routing_rule_set_version_id``, ``approval_request.routing_rule_id``,
``approval_decision.auto_rule_set_version_id`` and ``approval_decision.auto_rule_id``. 04 §18 rule
7(c) places T-REF-24 to T-REF-27 in PLF (PHASES BS-D-11).
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

# 04 §3 E-55.
RULE_SET_KIND = (
    "POB_ASSIGNMENT",
    "SSP_ASSIGNMENT",
    "APPROVAL_ROUTING",
    "AUTO_APPROVAL",
    "COMBINATION_DETECTION",
    "HOLD",
    "DATA_QUALITY",
)
# 04 T-REF-27 subject types: the configuration version tables a test case serves.
TEST_CASE_SUBJECTS = (
    "rule_set_version",
    "pob_template_version",
    "account_mapping_version",
    "registry_version",
)
# Foreign keys of revision 0013 tables to the rule set tables (DG-MIG-03).
REFERRING_COLUMNS = (
    ("approval_request", "routing_rule_set_version_id", "rule_set_version"),
    ("approval_request", "routing_rule_id", "rule"),
    ("approval_decision", "auto_rule_set_version_id", "rule_set_version"),
    ("approval_decision", "auto_rule_id", "rule"),
)


def _named(name: str) -> ops.NamedType:
    return ops.NamedType(name)


def _in_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("rule_set_kind", RULE_SET_KIND)
    ops.create_config_child_function()

    ops.create_tenant_table(
        "rule_set",
        sa.Column("code", _named("erev.code"), nullable=False),
        sa.Column("name", _named("erev.label"), nullable=False),
        sa.Column("kind", _named("erev.rule_set_kind"), nullable=False),
        sa.Column("description", _named("erev.memo"), nullable=True),
        standard_sets=["SC-C", "SC-M"],
        unique=[("ux_rule_set__code", ["tenant_id", "code"], None)],
    )
    ops.apply_class("rule_set", "IM-M")
    ops.enable_rls("rule_set", "RLS-T")

    ops.create_tenant_table(
        "rule_set_version",
        sa.Column("rule_set_id", sa.Uuid(), nullable=False),
        sa.Column("kind", _named("erev.rule_set_kind"), nullable=False),
        sa.Column("lint_result", _named("jsonb"), nullable=True),
        sa.Column("impact_simulation_file_id", sa.Uuid(), nullable=True),
        standard_sets=["SC-C", "SC-M", "SC-V"],
        unique=[
            ("ux_rule_set_version__no", ["tenant_id", "rule_set_id", "version_no"], None),
        ],
    )
    ops.add_tenant_fk("rule_set_version", "rule_set_id", "rule_set")
    ops.add_tenant_fk("rule_set_version", "impact_simulation_file_id", "file_object")
    ops.apply_class("rule_set_version", "IM-P")
    ops.enable_rls("rule_set_version", "RLS-T")
    ops.add_config_version_trigger("rule_set_version", scope_columns=["rule_set_id"])

    ops.create_tenant_table(
        "rule",
        sa.Column("rule_set_version_id", sa.Uuid(), nullable=False),
        sa.Column("rule_key", _named("erev.code"), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("conditions", _named("jsonb"), nullable=False),
        sa.Column("outputs", _named("jsonb"), nullable=False),
        sa.Column("specificity", sa.SmallInteger(), nullable=False),
        sa.Column("description", _named("erev.memo"), nullable=True),
        checks=[
            ("ck_rule__conditions", "jsonb_typeof(conditions) = 'array'"),
            ("ck_rule__outputs", "jsonb_typeof(outputs) = 'object'"),
            ("ck_rule__specificity", "specificity >= 0"),
        ],
        unique=[("ux_rule__key", ["tenant_id", "rule_set_version_id", "rule_key"], None)],
    )
    ops.add_tenant_fk("rule", "rule_set_version_id", "rule_set_version")
    ops.apply_class("rule", "IM-P", without_sc_m=True)
    ops.enable_rls("rule", "RLS-T")
    ops.add_config_child_trigger(
        "rule", parent_table="rule_set_version", parent_column="rule_set_version_id"
    )

    ops.create_tenant_table(
        "rule_test_case",
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("name", _named("erev.label"), nullable=False),
        sa.Column("input", _named("jsonb"), nullable=False),
        sa.Column("expected_output", _named("jsonb"), nullable=False),
        sa.Column("last_result", sa.Text(), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        standard_sets=["SC-C", "SC-M"],
        checks=[
            (
                "ck_rule_test_case__subject_type",
                f"subject_type IN ({_in_list(TEST_CASE_SUBJECTS)})",
            ),
            ("ck_rule_test_case__last_result", "last_result IN ('PASS', 'FAIL')"),
        ],
        indexes=[
            (
                "ix_rule_test_case__subject",
                ["tenant_id", "subject_type", "subject_id"],
                None,
            )
        ],
    )
    ops.apply_class("rule_test_case", "IM-P")
    ops.enable_rls("rule_test_case", "RLS-T")
    ops.add_config_child_trigger("rule_test_case", parent_table=None, parent_column="subject_id")

    for table, column, target in REFERRING_COLUMNS:
        ops.add_tenant_fk(table, column, target)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    for table, column, _ in reversed(REFERRING_COLUMNS):
        stem = column.removesuffix("_id")
        ops.execute(f"ALTER TABLE erev.{table} DROP CONSTRAINT fk_{table}__{stem}")
    ops.drop_tenant_table("rule_test_case")
    ops.drop_tenant_table("rule")
    ops.drop_tenant_table("rule_set_version")
    ops.drop_tenant_table("rule_set")
    ops.drop_config_child_function()
    ops.drop_enum("rule_set_kind")
