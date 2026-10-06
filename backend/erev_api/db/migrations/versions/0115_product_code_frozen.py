"""Lane ENG-FX, item PRODUCT-CODE-FREEZE-1 (supervisor ruling R-112 (i); number assigned by the
supervisor).

04 id amended (rev 1.160): DB-05 gains the code of a product in use. Contract lines, the product
pin of a computed contract and the engine's bundle name a product by its code, while SSP entries
and account mapping rules hold its id; a renamed product in use left the lines of its contracts
without an SSP entry, and their next computation failed with ``SSP_KEY_NOT_FOUND``.

- ``tg_product__code_frozen`` over the new function ``erev.tg_product__code_frozen()``: the
  ``code`` of T-REF-20 ``product`` changes only while no T-CON-10 ``obligation`` (a contract
  line), no T-REF-30 ``ssp_entry`` and no T-REF-15 ``account_mapping_rule`` references the product
  (DB-05, ``EREV-REF-001``). The three tables are RLS-T, so the trigger sees every reference of
  the tenant whatever the caller's entity scope. Every other column changes as before; the command
  refuses the same change first, by name (``reference.commands.update_product``).

One function and one trigger: the erev function count grows by one. The downgrade drops both.

Revision 0115 on 0113, main's head at this lane's merge of main 76fe6140 (supervisor ruling R-68
(e): a revision keeps its number and follows main's head at its merge). A revision imports nothing
of ``erev_api`` beyond the DDL helpers (DG-MIG-12).
"""

from __future__ import annotations

from erev_api.db import migration_ops as ops

revision = "0115"
down_revision = "0113"
branch_labels = None
depends_on = None

# DB-05 for T-REF-20: the code of a product that a contract line, an SSP entry or an account
# mapping rule references is frozen.
PRODUCT_CODE_FROZEN_BODY = """
BEGIN
  IF NEW.code IS NOT DISTINCT FROM OLD.code THEN
    RETURN NEW;
  END IF;
  IF EXISTS (
       SELECT 1 FROM erev.obligation o
        WHERE o.tenant_id = OLD.tenant_id AND o.product_id = OLD.id
     ) OR EXISTS (
       SELECT 1 FROM erev.ssp_entry e
        WHERE e.tenant_id = OLD.tenant_id AND e.product_id = OLD.id
     ) OR EXISTS (
       SELECT 1 FROM erev.account_mapping_rule r
        WHERE r.tenant_id = OLD.tenant_id AND r.product_id = OLD.id
     ) THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-REF-001: the code of product %s of %I.%I is frozen: a contract line, '
                       'an SSP entry or an account mapping rule references the product',
                       OLD.code, TG_TABLE_SCHEMA, TG_TABLE_NAME);
  END IF;
  RETURN NEW;
END
"""


def upgrade() -> None:
    """Add the DB-05 trigger of ``product``."""
    ops.create_trigger(
        "product", "code_frozen", PRODUCT_CODE_FROZEN_BODY, timing="BEFORE", events="UPDATE"
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created."""
    ops.execute("DROP TRIGGER tg_product__code_frozen ON erev.product")
    ops.execute("DROP FUNCTION erev.tg_product__code_frozen()")
