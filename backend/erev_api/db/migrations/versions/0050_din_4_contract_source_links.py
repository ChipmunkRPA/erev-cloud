"""BUILD_SPEC item DIN-4: contract source links.

04 ids created: T-CON-02 ``contract_source_link`` with ``ck_contract_source_link__link_role`` and
04 ``ux_contract_source_link`` named ``ux_contract_source_link__role`` (NC-16). The table is IM-A
(``apply_class``) and RLS-T. Foreign keys (NC-06): ``contract_id`` → ``contract``,
``source_record_id`` → ``source_record`` (0049) and ``contract_event_id`` → ``contract_event``
(0038). No type and no function is added.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

TABLE = "contract_source_link"
# 04 T-CON-02 ``link_role``.
LINK_ROLES = (
    "BOOKING",
    "AMENDMENT",
    "INVOICE",
    "USAGE",
    "PAYMENT",
    "DOCUMENT",
    "PROGRESS",
    "MIGRATION",
)
KEYS = (
    ("contract_id", "contract"),
    ("source_record_id", "source_record"),
    ("contract_event_id", "contract_event"),
)


def _uuid(name: str, *, nullable: bool) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    roles = ", ".join(f"'{role}'" for role in LINK_ROLES)
    ops.create_tenant_table(
        TABLE,
        _uuid("contract_id", nullable=False),
        _uuid("source_record_id", nullable=False),
        sa.Column("link_role", sa.Text(), nullable=False),
        _uuid("contract_event_id", nullable=True),
        standard_sets=["SC-C"],
        checks=[("ck_contract_source_link__link_role", f"link_role IN ({roles})")],
        unique=[
            (
                "ux_contract_source_link__role",
                ["tenant_id", "contract_id", "source_record_id", "link_role"],
                None,
            )
        ],
    )
    for column, target in KEYS:
        ops.add_tenant_fk(TABLE, column, target)
    ops.apply_class(TABLE, "IM-A")
    ops.enable_rls(TABLE, "RLS-T")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table(TABLE)
