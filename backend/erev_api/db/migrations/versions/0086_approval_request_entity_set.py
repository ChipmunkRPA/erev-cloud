"""Lane SECFIX-APR (supervisor ruling R-25 of 2026-09-30, findings SN-4 / SC-5; 04 T-PLT-17 rev
1.104; dev-guide DG-KRN-APR-06 rev 1.87): the entity set of an approval request.

04 ids amended: T-PLT-17 ``approval_request`` gains ``entity_ids`` (uuid[], NOT NULL, ``'{}'``) and
``is_all_entities`` (boolean, NOT NULL, ``false``) — the legal entities of a subject that spans
several (a combination or a regroup pair across entities, an import), frozen at submission, and
the marker of a subject that spans every entity of the tenant. A subject bound to ONE entity keeps
``entity_id`` (the RLS-TE key, unchanged); a tenant-level subject keeps all three empty.
``ck_approval_request__entity_scope`` holds the three forms apart: ``entity_id`` excludes a
non-empty ``entity_ids``, and ``is_all_entities`` excludes both.

The approval queue filters on these columns in SQL (``domain/platform/approval_queries.py``): a
request is listed for a scope that covers at least one entity of the set and is decidable only by
one authority that covers all of them (REQ-PLT-012). The set is stored because the queue is
paginated and counted in the database, and because a live derivation would drift once the
decision changes the subject (a combination applied, a proposal rejected).

No grant changes: the IM-S class of 0013 grants INSERT on the table and UPDATE on five listed
columns, and ``tg_approval_request__transition`` admits changes of those five only, so both new
columns are written once at INSERT and frozen afterwards. No function is added
(``tests/pg/test_migrations.py`` keeps its count). Rows written before this revision read as
tenant-level or single-entity requests, which is what they were (D-99: no backfill). Revision 0086,
the number assigned by the supervisor in the lane package, on 0115 — main's head at the merge
(0099 when the lane last merged main; the chain follows merge order, not number order: ruling
R-68 (e)); downgrade
removes exactly what upgrade created, in reverse order (DG-MIG-04).
"""

from __future__ import annotations

from typing import Final

from erev_api.db import migration_ops as ops

revision = "0086"
down_revision = "0115"
branch_labels = None
depends_on = None

TABLE: Final = "erev.approval_request"
CHECK: Final = "ck_approval_request__entity_scope"
# One entity (``entity_id``), several (``entity_ids``), every entity (``is_all_entities``) or none.
CHECK_SQL: Final = (
    "(entity_id IS NULL OR cardinality(entity_ids) = 0) "
    "AND (NOT is_all_entities OR (entity_id IS NULL AND cardinality(entity_ids) = 0))"
)


def upgrade() -> None:
    ops.execute(f"ALTER TABLE {TABLE} ADD COLUMN entity_ids uuid[] NOT NULL DEFAULT '{{}}'::uuid[]")
    ops.execute(f"ALTER TABLE {TABLE} ADD COLUMN is_all_entities boolean NOT NULL DEFAULT false")
    ops.execute(f"ALTER TABLE {TABLE} ADD CONSTRAINT {CHECK} CHECK ({CHECK_SQL})")


def downgrade() -> None:
    """Remove exactly what upgrade() created, in reverse order (DG-MIG-04)."""
    ops.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT {CHECK}")
    ops.execute(f"ALTER TABLE {TABLE} DROP COLUMN is_all_entities")
    ops.execute(f"ALTER TABLE {TABLE} DROP COLUMN entity_ids")
