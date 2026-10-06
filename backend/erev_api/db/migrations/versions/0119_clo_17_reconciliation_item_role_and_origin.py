"""BUILD_SPEC CLO-17, the role basis of the subledger-to-GL reconciliation and the late billing
document (supervisor rulings R-68 (a), R-69 and R-74 of 2026-09-30; 04 rev 1.253; number assigned by
the supervisor, register index 196): two columns and one item kind on T-CLS-07
``reconciliation_item``.

- ``account_role`` (text, NULL): the contract balance role of the ``totals`` row a subledger-to-GL
  item belongs to — the three roles compared on the role basis (R-74 (b)); NULL for an item of an
  account row and for every billing item. ``ck_reconciliation_item__account_role`` holds the
  three literals.
- ``origin_period_id`` (uuid, NULL): the period a billing document is dated in when it is compared
  in a later period because it was recorded after its own period's lock (R-68 (a)); NULL for a
  document compared in its own period. Foreign key to ``period``. The rule that writes it is not
  built with this revision: the column is NULL in every row until item R-68 (a) lands.
- ``item_kind`` admits ``NOT_STATED``: the one item of a role whose balance the subledger cannot
  state in the functional currency (R-74 (a)). ``ck_reconciliation_item__item_kind`` is replaced
  with the 0047 list plus that literal, and ``ck_reconciliation_item__not_stated`` holds what the
  kind means: the item names its role and carries no subledger amount.

Neither column is updatable: the IM-S column list of the table is unchanged, so the DB-03 function
``tg_reconciliation_item__transition()`` (which refuses every column outside that list) and the
column grants of ``erev_app`` stay as they are; INSERT is granted on the table. No table, type or
function is added (the erev function count is unchanged). No row is written (DG-MIG-07).

The downgrade removes exactly what the upgrade made, in reverse order (DG-MIG-04) — unless a row
carries ``NOT_STATED``: then it is REFUSED BY NAME (``EREV-MIG-0119``) and nothing is changed
(supervisor ruling of 2026-10-01 21:23 on the lane's pre-build line, form (2)). The refusal comes
from the constraint validation itself, inside the block that restores the 0047 kind list: an
``EXISTS`` over the table on the owner connection sees no tenant row (FORCE ROW LEVEL SECURITY),
while ``ADD CONSTRAINT`` scans every physical row (dev-guide DG-MIG-13; the form of 0067). Only
that ``check_violation`` is translated; the exception propagates, so the whole revision
transaction rolls back — the constraint dropped before the block included.

Why a refusal and not the kept-row form of 0111 (the check restored ``NOT VALID``, the rows
kept). Two facts part this revision from that one:

- The application of the earlier revision cannot read a kept row. Measured on main 5310275d — whose
  Alembic head is 0114 — over a database at this revision that holds one ``NOT_STATED`` item:
  ``GET /reconciliations/{id}/items`` of that reconciliation answers 500, because
  API-S-ReconciliationItem ``item_kind`` is a closed list of the seven earlier kinds there; the
  reconciliation itself (``GET /reconciliations/{id}``) and the list still answer 200. 0111's kept
  row stopped nothing; this one would take a screen of the close away.
- No provisioning seeds the literal: a ``NOT_STATED`` item exists only where a tenant attached a
  trial balance to a reconciliation one of whose roles could not be stated. A provisioned tenant
  without such a reconciliation holds none, so every walk over one (the downgrade witnesses of
  0067, 0084 and 0111) passes through this revision.

What the object can be and what the operator can do (supervisor ruling R-122 (b)). A
``NOT_STATED`` item belongs to a subledger-to-GL reconciliation that is ``DRAFT``, ``PREPARED``,
``REVIEWED``, ``CERTIFIED`` or ``REOPENED``, current or superseded by a later generation. In none
of these states does the application remove an item or change its kind: T-CLS-07 rows are never
deleted, and ``item_kind`` is outside the table's updatable columns. Generating the reconciliation
again writes a new row and leaves the old one. So no action in the product lifts the refusal: a
database that holds such an item stays at this revision or a later one, or is restored from a
backup taken before the item was written. The refusal says so.

A revision imports nothing of ``erev_api`` beyond the DDL helpers (DG-MIG-12): the literals are
written out. ``down_revision`` was main's head at each of the lane's merges of main (0114 when
built at 5310275d, 0104 at afb04675) and is 0118, the head at the supervisor's merge (ruling
R-68 (e)).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0119"
down_revision = "0118"
branch_labels = None
depends_on = None

TABLE: Final = "reconciliation_item"
KIND_CHECK: Final = "ck_reconciliation_item__item_kind"
ROLE_CHECK: Final = "ck_reconciliation_item__account_role"
NOT_STATED_CHECK: Final = "ck_reconciliation_item__not_stated"
ORIGIN_FK: Final = "fk_reconciliation_item__origin_period"
# 04 T-CLS-07 ``item_kind``: the list of revision 0047, then the literal of rev 1.253.
PREVIOUS_ITEM_KINDS: Final = (
    "UNMATCHED_SOURCE",
    "UNMATCHED_SUBLEDGER",
    "AMOUNT_VARIANCE",
    "UNPOSTED_BATCH",
    "TIMING",
    "DIRECT_GL_ENTRY",
    "OTHER",
)
ITEM_KINDS: Final = (*PREVIOUS_ITEM_KINDS, "NOT_STATED")
# 04 E-01 literals of the three contract balance roles (supervisor ruling R-74 (b)).
ACCOUNT_ROLES: Final = ("CONTRACT_LIABILITY", "CONTRACT_ASSET", "UNBILLED_RECEIVABLE")
# DG-MIG-13, the form of 0067: a constant statement (no interpolation). The 0047 kind list is
# restored INSIDE the block, and the constraint validation is the guard — it scans every physical
# row whatever row-level security hides from the owner connection. A NOT_STATED item does not
# satisfy the restored list: that check_violation alone is translated into the named refusal, and
# the RAISE propagates so that the whole revision transaction rolls back
# (transaction_per_migration). Nothing is deleted or rewritten; RLS and roles are untouched.
DOWNGRADE_RESTORE_KINDS: Final = """
DO $$
BEGIN
  ALTER TABLE erev.reconciliation_item DROP CONSTRAINT ck_reconciliation_item__item_kind;
  ALTER TABLE erev.reconciliation_item ADD CONSTRAINT ck_reconciliation_item__item_kind
    CHECK (item_kind IN ('UNMATCHED_SOURCE', 'UNMATCHED_SUBLEDGER', 'AMOUNT_VARIANCE',
                         'UNPOSTED_BATCH', 'TIMING', 'DIRECT_GL_ENTRY', 'OTHER'));
EXCEPTION
  WHEN check_violation THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'EREV-MIG-0119: reconciliation_item holds NOT_STATED items, written after '
                'revision 0119; the application of the earlier revision cannot read them (the '
                'items of such a reconciliation answer 500), and no action in the product '
                'removes an item or changes its kind. The downgrade is refused and nothing is '
                'changed: stay at revision 0119 or later, or restore a backup taken before the '
                'first such item was written';
END
$$;
"""


def _literals(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
    ops.execute(f"ALTER TABLE erev.{TABLE} ADD COLUMN origin_period_id uuid NULL")
    ops.execute(f"ALTER TABLE erev.{TABLE} ADD COLUMN account_role text NULL")
    ops.add_tenant_fk(TABLE, "origin_period_id", "period")
    ops.execute(
        f"ALTER TABLE erev.{TABLE} ADD CONSTRAINT {ROLE_CHECK} "
        f"CHECK (account_role IS NULL OR account_role IN ({_literals(ACCOUNT_ROLES)}))"
    )
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP CONSTRAINT {KIND_CHECK}")
    ops.execute(
        f"ALTER TABLE erev.{TABLE} ADD CONSTRAINT {KIND_CHECK} "
        f"CHECK (item_kind IN ({_literals(ITEM_KINDS)}))"
    )
    ops.execute(
        f"ALTER TABLE erev.{TABLE} ADD CONSTRAINT {NOT_STATED_CHECK} CHECK "
        "(item_kind <> 'NOT_STATED' OR (account_role IS NOT NULL AND subledger_amount IS NULL))"
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04); refused by name, with
    nothing changed, while a row carries ``NOT_STATED`` (module docstring)."""
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP CONSTRAINT {NOT_STATED_CHECK}")
    ops.execute(DOWNGRADE_RESTORE_KINDS)
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP CONSTRAINT {ROLE_CHECK}")
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP CONSTRAINT {ORIGIN_FK}")
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP COLUMN account_role")
    ops.execute(f"ALTER TABLE erev.{TABLE} DROP COLUMN origin_period_id")
