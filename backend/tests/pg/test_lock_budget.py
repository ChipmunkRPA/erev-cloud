"""05 §2.7 lock budget against a database migrated to head (SAR-40 ``lock-budget``; rev 1.53).

The partition lock footprint is a fact of the catalogue, so the shipped
``max_locks_per_transaction`` (compose command, Terraform default and floor) is held here against
the schema the revisions really create: a window extension or a further index on a partitioned
table that uses up the margin fails this module before it fails a deployment's rollout gate.
"""

from __future__ import annotations

import dataclasses
from uuid import uuid4

import pytest
from erev_api.controls.doctor import lock_budget, observe_lock_budget
from erev_api.db.lint import catalogue_connection
from erev_api.db.migration_ops import PARTITION_COLUMNS
from erev_api.db.session import DbContext, tenant_session
from sqlalchemy import text
from support.db import TestDatabase
from support.lock_budget import (
    compose_max_locks,
    terraform_max_locks_default,
    terraform_max_locks_floor,
)
from support.terraform import variable_default

pytestmark = pytest.mark.pg

# Parent, its (partitioned) indexes, its partitions and their indexes, per partitioned table.
_FAMILIES = text(
    """
    SELECT p.relname,
           1
           + (SELECT count(*) FROM pg_index x WHERE x.indrelid = p.oid)
           + (SELECT count(*) FROM pg_inherits i WHERE i.inhparent = p.oid)
           + (SELECT count(*) FROM pg_inherits i
              JOIN pg_index x ON x.indrelid = i.inhrelid WHERE i.inhparent = p.oid)
    FROM pg_class p
    JOIN pg_namespace n ON n.oid = p.relnamespace
    WHERE n.nspname = 'erev' AND p.relkind = 'p'
    ORDER BY p.relname
    """
)
# The relation locks this backend holds on one family.
_HELD = text(
    """
    WITH parent AS (SELECT CAST(:parent AS regclass) AS oid),
    family AS (
        SELECT oid FROM parent
        UNION ALL SELECT x.indexrelid FROM pg_index x, parent WHERE x.indrelid = parent.oid
        UNION ALL SELECT i.inhrelid FROM pg_inherits i, parent WHERE i.inhparent = parent.oid
        UNION ALL SELECT x.indexrelid FROM pg_inherits i
                  JOIN pg_index x ON x.indrelid = i.inhrelid, parent
                  WHERE i.inhparent = parent.oid
    )
    SELECT count(DISTINCT l.relation)
    FROM pg_locks l
    WHERE l.pid = pg_backend_pid() AND l.locktype = 'relation'
      AND l.relation IN (SELECT oid FROM family)
    """
)


def test_lock_budget_observation_is_what_postgresql_locks(test_database: TestDatabase) -> None:
    """The collector's footprint is the catalogue formula over exactly the 04 §1.6 tables, and the
    formula is what one statement locks: a read of ``schedule_line`` that names no month holds
    the parent, its partitioned indexes, every partition and every index of every partition until
    the transaction ends, while a read that names the month holds a handful."""
    # The doctor's own path: the catalogue connection as erev_app (no tenant context needed).
    with catalogue_connection(request_id="test-lock-budget") as connection:
        observation = observe_lock_budget(connection)
        families = {str(name): int(count) for name, count in connection.execute(_FAMILIES)}
    assert set(families) == set(PARTITION_COLUMNS)
    assert observation.partition_lock_footprint == sum(families.values())
    assert observation.relations > observation.partition_lock_footprint
    assert min(families.values()) > 900, families  # 181 partitions with four or five indexes each

    ctx = DbContext(tenant_id=uuid4(), user_id=None, entity_scope="*")
    with tenant_session(ctx, read_only=True) as session:
        session.execute(text("SELECT count(*) FROM erev.schedule_line"))
        unpruned = session.execute(_HELD, {"parent": "erev.schedule_line"}).scalar_one()
    assert unpruned == families["schedule_line"]
    with tenant_session(ctx, read_only=True) as session:
        session.execute(
            text(
                "SELECT count(*) FROM erev.schedule_line WHERE period_end_date = DATE '2026-01-31'"
            )
        )
        pruned = session.execute(_HELD, {"parent": "erev.schedule_line"}).scalar_one()
    assert pruned < 20 < unpruned


def test_shipped_lock_table_settings_cover_the_migrated_schema(
    test_database: TestDatabase,
) -> None:
    """The compose command, the Terraform default and the Terraform floor satisfy the rule with
    the live catalogue at the compose server's 100 connections and the Terraform default."""
    with catalogue_connection(request_id="test-lock-budget") as connection:
        live = observe_lock_budget(connection)
    hosted_connections = int(variable_default("db_max_connections") or 0)
    assert compose_max_locks() == terraform_max_locks_default()
    for connections in (100, hosted_connections):
        for setting in (compose_max_locks(), terraform_max_locks_floor()):
            shipped = dataclasses.replace(
                live,
                max_locks_per_transaction=setting,
                max_connections=connections,
                max_prepared_transactions=0,
            )
            result = lock_budget(shipped)
            assert result.ok, (setting, connections, result.lines())
        default = dataclasses.replace(
            live, max_locks_per_transaction=64, max_connections=connections
        )
        assert not lock_budget(default).ok
