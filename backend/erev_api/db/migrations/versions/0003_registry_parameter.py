"""BUILD_SPEC item FND-8: registry parameter catalogue.

04 ids created: E-53 ``registry_category`` and E-54 ``registry_scope``; T-PLT-31
``registry_parameter`` (IM-A, RLS-NONE-G, PT-N) with ``ux_registry_parameter__pol_id``, seeded
from ``registry.policies.POLICY_PARAMETERS`` and ``registry.platform.PLATFORM_PARAMETERS``
(DG-MIG-07); its DB-01 triggers ``tg_registry_parameter__immutable`` and
``tg_registry_parameter__truncate``; §14.2 grants (``SELECT`` to ``erev_app``).

The enum labels are pinned as literals at this revision's authoring state (DG-MIG-12; D-98
candidate 108): a revision never reads the live Python enum.
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops
from erev_api.registry.platform import PLATFORM_PARAMETERS
from erev_api.registry.policies import POLICY_PARAMETERS, RegistryParameterSpec

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# E-53 and E-54 at this revision (DG-MIG-12 literals).
REGISTRY_CATEGORY: tuple[str, ...] = (
    "ACCOUNTING_POLICY",
    "PRACTICAL_EXPEDIENT",
    "DISCLOSURE_ELECTION",
    "CLOSE",
    "PLATFORM",
    "SECURITY",
    "AI",
    "INTEGRATION",
)
REGISTRY_SCOPE: tuple[str, ...] = ("TENANT", "ENTITY", "BOOK", "PRODUCT", "CONTRACT", "OBLIGATION")

COLUMNS = (
    "code",
    "pol_id",
    "category",
    "value_schema",
    "default_asc606",
    "default_ifrs15",
    "is_forced_asc606",
    "is_forced_ifrs15",
    "legacy_parity_value",
    "allowed_levels",
    "pin",
    "approval_code",
    "description",
    "source_ref",
    "section",
)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _row(spec: RegistryParameterSpec) -> tuple[ops.SeedValue, ...]:
    # StrEnum members compare equal to their labels, so the literal order drives the array.
    levels = ",".join(level for level in REGISTRY_SCOPE if level in spec.allowed_levels)
    return (
        spec.code,
        spec.pol_id,
        spec.category.value,
        _json(spec.value_schema),
        # NOT NULL column: a parameter without a single framework default holds JSON null.
        _json(spec.default_asc606),
        None if spec.default_ifrs15 is None else _json(spec.default_ifrs15),
        spec.is_forced_asc606,
        spec.is_forced_ifrs15,
        None if spec.legacy_parity_value is None else _json(spec.legacy_parity_value),
        "{" + levels + "}",
        spec.pin,
        spec.approval_code,
        spec.description,
        spec.source_ref,
        spec.section,
    )


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("registry_category", REGISTRY_CATEGORY)
    ops.create_enum("registry_scope", REGISTRY_SCOPE)
    jsonb = ops.NamedType("jsonb")
    ops.create_global_table(
        "registry_parameter",
        sa.Column(
            "code",
            sa.Text(),
            sa.CheckConstraint(
                r"code ~ '^[a-z0-9_]+(\.[a-z0-9_]+)+$'", name="ck_registry_parameter__code"
            ),
            nullable=False,
        ),
        sa.Column("pol_id", sa.Text(), nullable=True),
        sa.Column("category", ops.NamedType("erev.registry_category"), nullable=False),
        sa.Column("value_schema", jsonb, nullable=False),
        sa.Column("default_asc606", jsonb, nullable=False),
        sa.Column("default_ifrs15", jsonb, nullable=True),
        sa.Column(
            "is_forced_asc606", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "is_forced_ifrs15", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("legacy_parity_value", jsonb, nullable=True),
        sa.Column("allowed_levels", ops.NamedType("erev.registry_scope[]"), nullable=False),
        sa.Column(
            "pin",
            sa.CHAR(1),
            sa.CheckConstraint("pin IN ('K','P')", name="ck_registry_parameter__pin"),
            nullable=False,
        ),
        sa.Column(
            "approval_code",
            sa.Text(),
            sa.CheckConstraint(
                "approval_code IN ('CFG','OVR','EST','JDG','FIX')",
                name="ck_registry_parameter__approval_code",
            ),
            nullable=False,
        ),
        sa.Column("description", ops.NamedType("erev.memo"), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("section", sa.Text(), nullable=False),
        primary_key=["code"],
        unique=[("ux_registry_parameter__pol_id", ["pol_id"], "pol_id IS NOT NULL")],
    )
    specs = (*POLICY_PARAMETERS.values(), *PLATFORM_PARAMETERS.values())
    ops.insert_rows("registry_parameter", COLUMNS, [_row(spec) for spec in specs])
    ops.apply_class("registry_parameter", "IM-A", global_reference=True)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_global_table("registry_parameter")
    ops.drop_enum("registry_scope")
    ops.drop_enum("registry_category")
