"""BUILD_SPEC item CTR-10: contract holds.

04 ids created: E-46 ``hold_source`` and T-CON-20 ``contract_hold``. E-45 ``hold_type`` exists since
revision 0039, which T-CON-11 ``hold_types`` needed (L3-1-Q-20), and is not created again.

- T-CON-20 ``contract_hold`` (IM-X, RLS-T, PT-N): the hold columns after SC-T, the partial index
  ``ix_contract_hold__open`` (``released_at IS NULL``), the check ``ck_contract_hold__release``
  (``released_event_id`` and ``released_at`` are set together), and the foreign keys to
  ``contract``, ``obligation``, ``rule_set_version``, ``rule`` and, for the applied and released
  events, ``contract_event``.

No function is added.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from erev_api.db import migration_ops as ops

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

TABLE = "contract_hold"
# 04 §3.4 E-46 (DG-MIG-06).
HOLD_SOURCE = ("SYSTEM", "USER_RULE", "MANUAL")


def _uuid(name: str, *, nullable: bool = True) -> sa.Column[Any]:
    return sa.Column(name, sa.Uuid(), nullable=nullable)


def _named(name: str, type_name: str, *, nullable: bool) -> sa.Column[Any]:
    return sa.Column(name, ops.NamedType(type_name), nullable=nullable)


def _timestamp(name: str, *, nullable: bool) -> sa.Column[Any]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_enum("hold_source", HOLD_SOURCE)
    ops.create_tenant_table(
        TABLE,
        _uuid("contract_id", nullable=False),
        _uuid("obligation_id"),
        _named("hold_type", "erev.hold_type", nullable=False),
        _named("hold_source", "erev.hold_source", nullable=False),
        _named("reason", "erev.memo", nullable=False),
        _uuid("rule_set_version_id"),
        _uuid("rule_id"),
        _uuid("applied_event_id", nullable=False),
        _timestamp("applied_at", nullable=False),
        _uuid("released_event_id"),
        _timestamp("released_at", nullable=True),
        checks=[
            (
                "ck_contract_hold__release",
                "(released_event_id IS NULL) = (released_at IS NULL)",
            )
        ],
        indexes=[("ix_contract_hold__open", ["tenant_id", "contract_id"], "released_at IS NULL")],
    )
    ops.add_tenant_fk(TABLE, "contract_id", "contract")
    ops.add_tenant_fk(TABLE, "obligation_id", "obligation")
    ops.add_tenant_fk(TABLE, "rule_set_version_id", "rule_set_version")
    ops.add_tenant_fk(TABLE, "rule_id", "rule")
    ops.add_tenant_fk(TABLE, "applied_event_id", "contract_event")
    ops.add_tenant_fk(TABLE, "released_event_id", "contract_event")
    ops.apply_class(TABLE, "IM-X")
    ops.enable_rls(TABLE, "RLS-T")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.drop_tenant_table(TABLE)
    ops.drop_enum("hold_source")
