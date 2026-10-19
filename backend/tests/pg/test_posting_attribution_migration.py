"""Posting attribution preserves its explicit tenant/posting key through an empty round trip."""

import pytest
from alembic import command
from sqlalchemy import text
from support.db import TestDatabase, alembic_config, fresh_head

pytestmark = pytest.mark.pg


def test_attribution_round_trip(test_database: TestDatabase) -> None:
    fresh_head()
    query = text("""
        SELECT column_name, data_type, is_nullable FROM information_schema.columns
        WHERE table_schema = 'erev' AND table_name = 'posting_attribution'
        ORDER BY ordinal_position
    """)
    with test_database.owner_engine.connect() as connection:
        before = connection.execute(query).all()
        primary = connection.scalar(
            text("""
            SELECT pg_get_constraintdef(oid) FROM pg_constraint
            WHERE conrelid = 'erev.posting_attribution'::regclass AND contype = 'p'
        """)
        )
    assert len(before) == 14
    assert primary == "PRIMARY KEY (tenant_id, subledger_posting_id)"
    command.downgrade(alembic_config(), "0167")
    with test_database.owner_engine.connect() as connection:
        assert connection.execute(query).all() == []
    command.upgrade(alembic_config(), "head")
    with test_database.owner_engine.connect() as connection:
        assert connection.execute(query).all() == before
