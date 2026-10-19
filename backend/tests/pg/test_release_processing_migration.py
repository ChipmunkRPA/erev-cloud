"""Empty-schema upgrade/downgrade preserves the processing event schema."""

import pytest
from alembic import command
from sqlalchemy import text
from support.db import TestDatabase, alembic_config, fresh_head

pytestmark = pytest.mark.pg


def test_release_processing_round_trip(test_database: TestDatabase) -> None:
    fresh_head()
    query = text("""
        SELECT column_name, data_type, is_nullable FROM information_schema.columns
        WHERE table_schema = 'erev' AND table_name = 'release_group_processing'
        ORDER BY ordinal_position
    """)
    with test_database.owner_engine.connect() as connection:
        before = connection.execute(query).all()
    assert len(before) == 16
    command.downgrade(alembic_config(), "0165")
    with test_database.owner_engine.connect() as connection:
        assert connection.execute(query).all() == []
    command.upgrade(alembic_config(), "head")
    with test_database.owner_engine.connect() as connection:
        assert connection.execute(query).all() == before
