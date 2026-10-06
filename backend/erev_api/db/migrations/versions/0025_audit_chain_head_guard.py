"""BUILD_SPEC item WEB-3a: audit chain head guard.

04 ids extended: DB-09 gains ``tg_audit_chain_head__guard`` on T-PLT-22 ``audit_chain_head``
(01-DECISIONS D-80, audit chain anchoring). No table, column or enum changes.
"""

from __future__ import annotations

from erev_api.db import migration_ops as ops

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

# D-80 rule 3: the head advances only from inside tg_audit_event__chain, which runs its UPDATE at
# trigger depth 1, so this trigger fires at depth 2; and only to the next position.
AUDIT_CHAIN_HEAD_GUARD_BODY = """
BEGIN
  IF pg_trigger_depth() < 2 OR NEW.last_chain_seq IS DISTINCT FROM OLD.last_chain_seq + 1 THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = format('EREV-AUD-001: the audit chain head of tenant %s advances only through an '
                       'appended audit event', OLD.tenant_id);
  END IF;
  RETURN NEW;
END
"""


def upgrade() -> None:
    """Create the item's objects through the §6.5 helpers, in 04 §18 dependency order."""
    ops.create_trigger(
        "audit_chain_head", "guard", AUDIT_CHAIN_HEAD_GUARD_BODY, timing="BEFORE", events="UPDATE"
    )


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.execute("DROP TRIGGER tg_audit_chain_head__guard ON erev.audit_chain_head")
    ops.execute("DROP FUNCTION erev.tg_audit_chain_head__guard()")
