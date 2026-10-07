"""Keep the FX layer lookup keys usable under row-level security.

Enum equality is not leakproof. A book_code key before layer_key prevents PostgreSQL from
using the later key as an index condition under RLS. Keep the enum as the final key.
No accounting data, grants or policies change; downgrade restores the previous key order.
"""

from erev_api.db import migration_ops as ops

revision = "0136"
down_revision = "0135"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.execute("DROP INDEX erev.ix_fx_layer_movement__layer")
    ops.execute("""
        CREATE INDEX ix_fx_layer_movement__layer ON erev.fx_layer_movement
        (tenant_id, contract_id, layer_key, book_code)
    """)


def downgrade() -> None:
    ops.execute("DROP INDEX erev.ix_fx_layer_movement__layer")
    ops.execute("""
        CREATE INDEX ix_fx_layer_movement__layer ON erev.fx_layer_movement
        (tenant_id, contract_id, book_code, layer_key)
    """)
