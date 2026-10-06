"""D-93 (4) / D-97 (3): E-49 ``ssp_value_basis`` gains ``PER_INCREMENT`` and ``PER_BOOKED_TERM``;
T-REF-30 gains ``quantity_unit`` (E-131 ``ssp_quantity_unit``).

04 ids amended: E-49 and E-131 (rev 1.41), T-REF-30 ``value_basis`` note and ``quantity_unit``
column. A series product's SSP entry declares the pricing basis the ENGINE_SPEC S06-R-11 series
row reads at a modification boundary: one increment (``PER_INCREMENT``), the booked term in force
(``PER_BOOKED_TERM``) or the remaining increments at d as today (``AMOUNT``); a ``PER_INCREMENT``
entry also declares what the line's quantity counts — ``SERVICE_UNITS`` (each unit spans the term)
or ``INCREMENTS`` (the quantity counts increments) — with no default and never inferred, and the
unit is meaningful for ``PER_INCREMENT`` only (D-97 (3)):
``CHECK ((value_basis::text = 'PER_INCREMENT') = (quantity_unit IS NOT NULL))``. Two labels are
appended to the basis type; the unit type, the nullable column and the check are created; no
default changes.
The downgrade drops the check, the column and the unit type and removes the two labels through
``remove_enum_value``, which fails when a stored row still uses one of them (DG-MIG-06). No
backfill: no production data exists before release (D-97 (3a)).

Revision 0060 follows 0059 (lane F-CLO's ``clo_6_reconciliation_period_lock_id``): authored as
0056 on 0054, held out of the tree while 0055 (P5), 0056 (F-LMG), 0057 (SOP-1), 0058 (F-ADM) and
0059 landed, and re-parented at the supervisor's assignment (single head). Labels are literals
and the module imports ``migration_ops`` only (DG-MIG-12).
"""

from __future__ import annotations

from erev_api.db import migration_ops as ops

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None

ENUM = "ssp_value_basis"
VALUES = ("PER_INCREMENT", "PER_BOOKED_TERM")
UNIT_ENUM = "ssp_quantity_unit"
UNIT_VALUES = ("SERVICE_UNITS", "INCREMENTS")
TABLE = "ssp_entry"
COLUMN = "quantity_unit"
CHECK = "ck_ssp_entry__quantity_unit_per_increment"


def upgrade() -> None:
    for value in VALUES:
        ops.add_enum_value(ENUM, value)
    ops.create_enum(UNIT_ENUM, UNIT_VALUES)
    ops.execute(f"ALTER TABLE erev.{TABLE} ADD COLUMN {COLUMN} erev.{UNIT_ENUM}")
    # The check compares the basis as text: the label PER_INCREMENT is added by this same revision
    # and PostgreSQL refuses a new enum value as an enum literal before the transaction commits
    # ("unsafe use of new value"); the text comparison is exact and needs no enum input.
    ops.execute(
        f"ALTER TABLE erev.{TABLE} ADD CONSTRAINT {CHECK} "
        f"CHECK ((value_basis::text = 'PER_INCREMENT') = ({COLUMN} IS NOT NULL))"
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP CONSTRAINT {CHECK}")
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP COLUMN {COLUMN}")
    ops.drop_enum(UNIT_ENUM)
    for value in reversed(VALUES):
        ops.remove_enum_value(ENUM, value)
