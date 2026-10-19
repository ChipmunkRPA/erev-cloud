"""The release fence covers every population input, including partition descendants."""

import pytest
from sqlalchemy import text
from support.db import TestDatabase

pytestmark = pytest.mark.pg


def test_population_writer_trigger_coverage(test_database: TestDatabase) -> None:
    expected = {
        "book",
        "combination_group",
        "combination_group_member",
        "contract",
        "contract_event",
        "contract_version",
        "obligation_version",
        "period",
        "period_state",
        "subledger_line",
        "subledger_posting",
        "subledger_posting_seal",
    }
    with test_database.owner_engine.connect() as connection:
        rows = connection.execute(
            text("""
            SELECT c.relname, t.tgtype, t.tgenabled
            FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'erev' AND NOT c.relispartition
              AND t.tgname LIKE '%__validation_population'
        """)
        ).all()
        assert {row.relname for row in rows} == expected
        # ROW=1, BEFORE=2, INSERT=4, DELETE=8, UPDATE=16.
        assert all(row.tgtype == 31 and row.tgenabled == "O" for row in rows)
        missing = connection.execute(
            text("""
            WITH RECURSIVE descendants AS (
                SELECT c.oid FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'erev' AND c.relname = ANY(:tables)
                UNION ALL
                SELECT i.inhrelid FROM pg_inherits i JOIN descendants d ON d.oid = i.inhparent
            )
            SELECT d.oid::regclass::text FROM descendants d
            WHERE NOT EXISTS (
                SELECT 1 FROM pg_trigger t WHERE t.tgrelid = d.oid
                  AND t.tgname LIKE '%__validation_population' AND t.tgenabled = 'O'
            )
        """),
            {"tables": sorted(expected)},
        ).all()
        assert missing == []
