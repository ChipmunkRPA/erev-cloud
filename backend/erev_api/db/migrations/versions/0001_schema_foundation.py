"""BUILD_SPEC item FND-6: schema foundation.

04 ids created: §18 step 0001 (schema ``erev`` through env.py); TY-01 to TY-10 (domains
``erev.money``, ``exact``, ``fx_rate``, ``currency_code``, ``sha256``, ``code``, ``label``,
``memo``, ``email``, ``tz_name``); sequences ``erev.contract_event_record_seq`` and
``erev.security_event_seq``; §1.4 functions ``erev.current_tenant_id()``,
``erev.current_user_id()`` and ``erev.entity_in_scope(uuid)``; DB-01
``erev.tg_forbid_mutation()``; DB-02 ``erev.tg_touch()``; §14.2 grants on the schema, the
sequences and the functions to ``erev_app``.
"""

from __future__ import annotations

from erev_api.db import migration_ops as ops

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    ops.create_schema_foundation()


def downgrade() -> None:
    ops.drop_schema_foundation()
