"""The frozen-validation file purpose upgrades and downgrades on an empty database."""

import pytest
from alembic import command
from sqlalchemy import text
from support.db import TestDatabase, alembic_config, fresh_head

pytestmark = pytest.mark.pg


def test_validation_dataset_enum_round_trip(test_database: TestDatabase) -> None:
    fresh_head()
    query = text("SELECT enum_range(NULL::erev.file_purpose)::text")
    with test_database.owner_engine.connect() as connection:
        expected = connection.scalar(query)
    assert "VALIDATION_DATASET" in expected
    command.downgrade(alembic_config(), "0162")
    with test_database.owner_engine.connect() as connection:
        assert "VALIDATION_DATASET" not in connection.scalar(query)
    command.upgrade(alembic_config(), "head")
    with test_database.owner_engine.connect() as connection:
        assert connection.scalar(query) == expected
