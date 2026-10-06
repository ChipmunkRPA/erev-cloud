"""D-87 L6-5-Q-18: functional consideration payable and customer incentive asset (T-CON-09).

04 ids amended: T-CON-09 ``contract_version_balance`` gains ``consideration_payable_functional``
and ``customer_incentive_asset_functional`` (erev.money, NOT NULL DEFAULT 0), with the checks
``ck_contract_version_balance__consideration_payable_functional`` and
``ck_contract_version_balance__incentive_asset_functional`` (labelled balances are non-negative;
the second name is shortened to fit the 63-byte identifier limit). The payable is the open layers
at the closing rate (S12-R-21); the asset is historical functional at spot on the promise date less
releases at historical carrying, never remeasured (POL-164).

Two columns are added; no table, function or trigger. This is the only Alembic revision of Level 7
(D-87 L6-5-Q-18).
"""

from __future__ import annotations

from erev_api.db import migration_ops as ops

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

TABLE = "contract_version_balance"
# (column, check constraint)
COLUMNS = (
    (
        "consideration_payable_functional",
        "ck_contract_version_balance__consideration_payable_functional",
    ),
    (
        "customer_incentive_asset_functional",
        "ck_contract_version_balance__incentive_asset_functional",
    ),
)


def upgrade() -> None:
    """Add the two T-CON-09 functional columns and their non-negative checks."""
    for column, check in COLUMNS:
        ops.execute(f"ALTER TABLE erev.{TABLE} ADD COLUMN {column} erev.money NOT NULL DEFAULT 0")
        ops.execute(f"ALTER TABLE erev.{TABLE} ADD CONSTRAINT {check} CHECK ({column} >= 0)")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    for column, check in reversed(COLUMNS):
        ops.execute(f"ALTER TABLE erev.{TABLE} DROP CONSTRAINT {check}")
        ops.execute(f"ALTER TABLE erev.{TABLE} DROP COLUMN {column}")
