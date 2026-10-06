"""BUILD_SPEC item FND-7: global catalogues.

04 ids created: T-REF-08 ``currency`` (IM-A, RLS-NONE-G, PT-N), seeded from
``erev_engine.currencies.ISO_4217``; T-PLT-11 ``permission`` (IM-A, RLS-NONE-G, PT-N), seeded from
``erev_api.auth.permissions.CATALOGUE`` (DG-KRN-PERM-01, DG-MIG-07); their DB-01 triggers
``tg_currency__immutable``, ``tg_currency__truncate``, ``tg_permission__immutable`` and
``tg_permission__truncate``; §14.2 grants (``SELECT`` to ``erev_app``).
"""

from __future__ import annotations

import sqlalchemy as sa
from erev_api.auth.permissions import CATALOGUE
from erev_api.db import migration_ops as ops
from erev_engine.currencies import ISO_4217

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_global_table(
        "currency",
        sa.Column("code", ops.NamedType("erev.currency_code"), nullable=False),
        sa.Column("numeric_code", sa.CHAR(3), nullable=False),
        sa.Column("name", ops.NamedType("erev.label"), nullable=False),
        sa.Column(
            "minor_unit",
            sa.SmallInteger(),
            sa.CheckConstraint("minor_unit BETWEEN 0 AND 4", name="ck_currency__minor_unit"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        primary_key=["code"],
    )
    ops.insert_rows(
        "currency",
        ("code", "numeric_code", "name", "minor_unit"),
        [(c.code, c.numeric_code, c.name, c.minor_unit) for c in ISO_4217.values()],
    )
    ops.apply_class("currency", "IM-A", global_reference=True)

    ops.create_global_table(
        "permission",
        sa.Column(
            "code",
            sa.Text(),
            sa.CheckConstraint(r"code ~ '^[a-z_]+(\.[a-z_]+)+$'", name="ck_permission__code"),
            nullable=False,
        ),
        sa.Column("area", sa.Text(), nullable=False),
        sa.Column("description", ops.NamedType("erev.label"), nullable=False),
        sa.Column("is_approval", sa.Boolean(), nullable=False),
        sa.Column("is_access_admin", sa.Boolean(), nullable=False),
        sa.Column("requires_mfa", sa.Boolean(), nullable=False),
        primary_key=["code"],
    )
    ops.insert_rows(
        "permission",
        ("code", "area", "description", "is_approval", "is_access_admin", "requires_mfa"),
        [
            (p.code, p.area, p.description, p.is_approval, p.is_access_admin, p.requires_mfa)
            for p in CATALOGUE
        ],
    )
    ops.apply_class("permission", "IM-A", global_reference=True)


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_global_table("permission")
    ops.drop_global_table("currency")
