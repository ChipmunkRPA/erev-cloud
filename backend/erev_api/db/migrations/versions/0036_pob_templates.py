"""BUILD_SPEC item RFD-10: obligation templates.

04 ids created: E-11 ``recognition_method``, E-18 ``obligation_kind``, E-19
``satisfaction_pattern``, E-20 ``over_time_criterion``, E-21 ``ratable_convention``, E-90
``licence_nature`` and E-91 ``warranty_type`` (04 §3.4 order; E-89 and E-105 exist from revision
0033); T-REF-22 ``pob_template`` (IM-M, RLS-T) with ``ux_pob_template__code``; T-REF-23
``pob_template_version`` (IM-P, SC-V, RLS-T) with ``ux_pob_template_version__no``, the 04 column
checks named ``ck_pob_template_version__series_increment_unit``, ``__series``,
``__over_time_criterion``, ``__point_in_time_method``, ``__ratable_convention``,
``__start_date_rule`` and ``__end_date_rule`` (NC-16), ``ck_pob_template_version__term_months``
("Required for START_PLUS_TERM") and the JSON object checks ``__disaggregation``,
``__account_role_overrides`` and ``__policy_values``, the foreign key ``pob_template_id`` →
``pob_template`` and the DB-04 trigger ``tg_pob_template_version__config_version`` with scope key
``pob_template_id`` (PUBLISHED ranges of one template never overlap). The foreign key
``product.default_pob_template_id`` → ``pob_template`` of T-REF-20 is added here, because this
revision creates ``pob_template`` (DG-MIG-03). ``rule_test_case`` rows of subject type
``pob_template_version`` follow the existing polymorphic DB-04 child trigger. No function is added.
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None

# 04 §3.4 E-11, E-18 to E-21, E-90 and E-91 (DG-MIG-06).
RECOGNITION_METHOD = (
    "POINT_IN_TIME",
    "TIME_ELAPSED",
    "UNITS_DELIVERED",
    "OUTPUT_PERCENT",
    "MILESTONE",
    "COST_TO_COST",
    "LABOUR_HOURS",
    "RIGHT_TO_INVOICE",
    "COST_RECOVERY",
    "USAGE",
    "ROYALTY",
    "REDEMPTION_PATTERN",
    "MANUAL",
)
OBLIGATION_KIND = (
    "STANDARD",
    "VC_LINE",
    "MATERIAL_RIGHT",
    "SERVICE_WARRANTY",
    "CUSTODIAL",
    "LICENCE",
    "SHIPPING",
)
SATISFACTION_PATTERN = ("POINT_IN_TIME", "OVER_TIME")
OVER_TIME_CRITERION = ("OT_A", "OT_B", "OT_C", "NOT_APPLICABLE")
RATABLE_CONVENTION = ("DAILY", "MONTHLY_EVEN", "MID_MONTH")
LICENCE_NATURE = ("FUNCTIONAL", "SYMBOLIC", "NOT_APPLICABLE")
WARRANTY_TYPE = ("ASSURANCE", "SERVICE", "NONE")


def _jsonb_object(name: str) -> sa.Column[object]:
    return sa.Column(
        name, ops.NamedType("jsonb"), nullable=False, server_default=sa.text("'{}'::jsonb")
    )


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("recognition_method", RECOGNITION_METHOD)
    ops.create_enum("obligation_kind", OBLIGATION_KIND)
    ops.create_enum("satisfaction_pattern", SATISFACTION_PATTERN)
    ops.create_enum("over_time_criterion", OVER_TIME_CRITERION)
    ops.create_enum("ratable_convention", RATABLE_CONVENTION)
    ops.create_enum("licence_nature", LICENCE_NATURE)
    ops.create_enum("warranty_type", WARRANTY_TYPE)

    ops.create_tenant_table(
        "pob_template",
        sa.Column("code", ops.NamedType("erev.code"), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column("description", ops.NamedType("erev.memo"), nullable=True),
        standard_sets=["SC-C", "SC-M"],
        unique=[("ux_pob_template__code", ["tenant_id", "code"], None)],
    )
    ops.apply_class("pob_template", "IM-M")
    ops.enable_rls("pob_template", "RLS-T")

    ops.create_tenant_table(
        "pob_template_version",
        sa.Column("pob_template_id", sa.Uuid(), nullable=False),
        sa.Column(
            "obligation_kind",
            ops.NamedType("erev.obligation_kind"),
            nullable=False,
            server_default=sa.text("'STANDARD'"),
        ),
        sa.Column(
            "distinctness",
            ops.NamedType("erev.distinctness"),
            nullable=False,
            server_default=sa.text("'distinct'"),
        ),
        sa.Column("series_increment_unit", sa.Text(), nullable=True),
        sa.Column(
            "satisfaction_pattern", ops.NamedType("erev.satisfaction_pattern"), nullable=False
        ),
        sa.Column(
            "over_time_criterion",
            ops.NamedType("erev.over_time_criterion"),
            nullable=False,
            server_default=sa.text("'NOT_APPLICABLE'"),
        ),
        sa.Column("recognition_method", ops.NamedType("erev.recognition_method"), nullable=False),
        sa.Column("ratable_convention", ops.NamedType("erev.ratable_convention"), nullable=True),
        sa.Column(
            "start_date_rule", sa.Text(), nullable=False, server_default=sa.text("'LINE_START'")
        ),
        sa.Column("end_date_rule", sa.Text(), nullable=False, server_default=sa.text("'LINE_END'")),
        sa.Column("term_months", sa.Integer(), nullable=True),
        sa.Column(
            "principal_agent",
            ops.NamedType("erev.principal_agent"),
            nullable=False,
            server_default=sa.text("'PRINCIPAL'"),
        ),
        sa.Column(
            "warranty_type",
            ops.NamedType("erev.warranty_type"),
            nullable=False,
            server_default=sa.text("'NONE'"),
        ),
        sa.Column(
            "licence_nature",
            ops.NamedType("erev.licence_nature"),
            nullable=False,
            server_default=sa.text("'NOT_APPLICABLE'"),
        ),
        sa.Column(
            "sfc_assessment_required", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("revenue_category", sa.Text(), nullable=True),
        _jsonb_object("disaggregation"),
        _jsonb_object("account_role_overrides"),
        sa.Column("stratification_label", sa.Text(), nullable=True),
        sa.Column(
            "is_excluded_from_netting_attribution",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        _jsonb_object("policy_values"),
        standard_sets=["SC-C", "SC-M", "SC-V"],
        checks=[
            (
                "ck_pob_template_version__series_increment_unit",
                "series_increment_unit IN ('day', 'month', 'transaction', 'unit')",
            ),
            (
                "ck_pob_template_version__series",
                "(distinctness = 'series') = (series_increment_unit IS NOT NULL)",
            ),
            (
                "ck_pob_template_version__over_time_criterion",
                "(satisfaction_pattern = 'OVER_TIME') = (over_time_criterion <> 'NOT_APPLICABLE')",
            ),
            (
                "ck_pob_template_version__point_in_time_method",
                "satisfaction_pattern <> 'POINT_IN_TIME' "
                "OR recognition_method IN ('POINT_IN_TIME', 'UNITS_DELIVERED', 'MANUAL')",
            ),
            (
                "ck_pob_template_version__ratable_convention",
                "(recognition_method = 'TIME_ELAPSED') = (ratable_convention IS NOT NULL)",
            ),
            (
                "ck_pob_template_version__start_date_rule",
                "start_date_rule IN ('LINE_START', 'BOOKING_DATE', 'CONTROL_TRANSFER', "
                "'FIRST_USAGE', 'LICENCE_START_OR_AVAILABLE')",
            ),
            (
                "ck_pob_template_version__end_date_rule",
                "end_date_rule IN ('LINE_END', 'START_PLUS_TERM', 'NONE')",
            ),
            # [J] 04 "Required for START_PLUS_TERM", and a positive term (L2-1-Q-44).
            (
                "ck_pob_template_version__term_months",
                "(end_date_rule <> 'START_PLUS_TERM' OR term_months IS NOT NULL) "
                "AND (term_months IS NULL OR term_months > 0)",
            ),
            # [J] As for product.disaggregation and product.policy_values (revision 0033).
            ("ck_pob_template_version__disaggregation", "jsonb_typeof(disaggregation) = 'object'"),
            (
                "ck_pob_template_version__account_role_overrides",
                "jsonb_typeof(account_role_overrides) = 'object'",
            ),
            ("ck_pob_template_version__policy_values", "jsonb_typeof(policy_values) = 'object'"),
        ],
        unique=[
            (
                "ux_pob_template_version__no",
                ["tenant_id", "pob_template_id", "version_no"],
                None,
            )
        ],
    )
    ops.add_tenant_fk("pob_template_version", "pob_template_id", "pob_template")
    ops.apply_class("pob_template_version", "IM-P")
    ops.enable_rls("pob_template_version", "RLS-T")
    ops.add_config_version_trigger("pob_template_version", scope_columns=["pob_template_id"])

    ops.add_tenant_fk("product", "default_pob_template_id", "pob_template")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.execute("ALTER TABLE erev.product DROP CONSTRAINT fk_product__default_pob_template")
    ops.drop_tenant_table("pob_template_version")
    ops.drop_tenant_table("pob_template")
    ops.drop_enum("warranty_type")
    ops.drop_enum("licence_nature")
    ops.drop_enum("ratable_convention")
    ops.drop_enum("over_time_criterion")
    ops.drop_enum("satisfaction_pattern")
    ops.drop_enum("obligation_kind")
    ops.drop_enum("recognition_method")
