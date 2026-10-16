"""Revision 0161 empty-schema round trip and app-role lint."""

import pytest
from alembic import command
from sqlalchemy import text
from support.db import TestDatabase, alembic_config, fresh_head

pytestmark = pytest.mark.pg


def test_release_verification_empty_schema_round_trip(test_database: TestDatabase) -> None:
    fresh_head()
    query = text("""
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'erev' AND table_name IN (
            'release_validation', 'release_validation_attempt',
            'release_validation_group', 'computation_verification')
        ORDER BY table_name, ordinal_position
    """)
    with test_database.owner_engine.connect() as connection:
        before = connection.execute(query).all()
    assert before
    command.downgrade(alembic_config(), "0160")
    with test_database.owner_engine.connect() as connection:
        assert connection.execute(query).all() == []
    command.upgrade(alembic_config(), "head")
    test_database.app_engine.dispose()
    with test_database.owner_engine.connect() as connection:
        assert connection.execute(query).all() == before
