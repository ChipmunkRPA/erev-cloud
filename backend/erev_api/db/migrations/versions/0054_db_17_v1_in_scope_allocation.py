"""D-88 L7-5-Q-6: DB-17 V1 sums the in-scope obligation versions of a contract version.

04 ids amended: DB-17 V1 (``tg_contract_version__allocation``, ``EREV-ALC-001``) sums
``obligation_version.allocated_amount`` over the rows with ``scope_flag = 'IN_SCOPE_606'`` against
``transaction_price − consideration_payable_amount``. The engine publishes the transaction price
net of the allocation of routed-out ``LEASE_842`` obligations while the allocation pool stays gross
(POLICIES PT-09; S03-R-11), so the lease rows leave the sum.

``CREATE OR REPLACE`` keeps the function's grants and its deferred constraint trigger; no table,
column, function or trigger is added. This is the only Alembic revision of Level 8 (D-88
L7-5-Q-6).
"""

from __future__ import annotations

from erev_api.db import migration_ops as ops

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

SIGNATURE = "tg_contract_version__allocation()"

# DB-17 V1 as amended by D-88 L7-5-Q-6: only IN_SCOPE_606 rows allocate the transaction price.
ALLOCATION_BODY = """
DECLARE
  allocated numeric;
BEGIN
  SELECT coalesce(sum(o.allocated_amount), 0) INTO allocated
    FROM erev.obligation_version o
   WHERE o.tenant_id = NEW.tenant_id AND o.contract_version_id = NEW.id
     AND o.scope_flag = 'IN_SCOPE_606';
  IF allocated IS DISTINCT FROM NEW.transaction_price - NEW.consideration_payable_amount THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-ALC-001: obligation versions of contract version %s allocate %s, not '
                       'transaction_price %s less consideration_payable_amount %s',
                       NEW.id, allocated, NEW.transaction_price, NEW.consideration_payable_amount);
  END IF;
  RETURN NULL;
END
"""

# The body of 0039 (04 §14.1 rev 1.2), restored by downgrade().
ALLOCATION_0039_BODY = """
DECLARE
  allocated numeric;
BEGIN
  SELECT coalesce(sum(o.allocated_amount), 0) INTO allocated
    FROM erev.obligation_version o
   WHERE o.tenant_id = NEW.tenant_id AND o.contract_version_id = NEW.id;
  IF allocated IS DISTINCT FROM NEW.transaction_price - NEW.consideration_payable_amount THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-ALC-001: obligation versions of contract version %s allocate %s, not '
                       'transaction_price %s less consideration_payable_amount %s',
                       NEW.id, allocated, NEW.transaction_price, NEW.consideration_payable_amount);
  END IF;
  RETURN NULL;
END
"""


def _replace_function(signature: str, body: str) -> None:
    """``CREATE OR REPLACE`` keeps the function's grants and its trigger; NC-18 attributes."""
    ops.execute(
        f"CREATE OR REPLACE FUNCTION erev.{signature} RETURNS trigger LANGUAGE plpgsql "
        f"SECURITY INVOKER SET search_path = erev, pg_catalog\n  AS $fn${body}$fn$"
    )


def upgrade() -> None:
    """DB-17 V1 over the IN_SCOPE_606 obligation versions."""
    _replace_function(SIGNATURE, ALLOCATION_BODY)


def downgrade() -> None:
    """Restore the 0039 body exactly (DG-MIG-04)."""
    _replace_function(SIGNATURE, ALLOCATION_0039_BODY)
