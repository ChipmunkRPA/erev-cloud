"""Alembic environment (docs/dev-guide.md §6.5 DG-MIG-01; 04 §18 rule 1).

Revisions run as ``erev_owner`` over the selected environment's owner URL, behind the DG-ENV-12
role guard, one transaction per revision, with the version table in schema ``erev``.

The version table needs schema ``erev`` before the first revision runs, so this environment
creates the schema when it is absent. When a downgrade leaves no revision applied, it drops the
version table and then the schema without CASCADE: the drop fails if any application object
remains (DG-MIG-05).
"""

from __future__ import annotations

from alembic import context
from erev_api.db.session import APP_ROLE, migration_engine

SCHEMA = "erev"
VERSION_TABLE = "alembic_version"


def run_migrations_online() -> None:
    engine = migration_engine()
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
            connection.commit()
            context.configure(
                connection=connection,
                version_table=VERSION_TABLE,
                version_table_schema=SCHEMA,
                transaction_per_migration=True,
            )
            with context.begin_transaction():
                context.run_migrations()
            if context.get_context().get_current_heads():
                # readyz compares the applied revision with the code head as erev_app (OPR-23).
                connection.exec_driver_sql(
                    f"GRANT SELECT ON {SCHEMA}.{VERSION_TABLE} TO {APP_ROLE}"
                )
            else:
                connection.exec_driver_sql(f"DROP TABLE IF EXISTS {SCHEMA}.{VERSION_TABLE}")
                connection.exec_driver_sql(f"DROP SCHEMA {SCHEMA}")
            connection.commit()
    finally:
        engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("offline SQL generation is not supported; revisions run as erev_owner")
run_migrations_online()
