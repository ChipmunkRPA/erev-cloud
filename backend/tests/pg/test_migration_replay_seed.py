"""Replay seed installs on existing databases and survives append-only seed downgrade."""

import pytest
from alembic import command
from sqlalchemy import text
from support.db import TestDatabase, alembic_config, fresh_head

pytestmark = pytest.mark.pg


def test_replay_seed_existing_database_and_round_trip(test_database: TestDatabase) -> None:
    fresh_head()
    query = text("SELECT * FROM erev.registry_parameter WHERE code = 'platform.replay_seed'")
    with test_database.owner_engine.connect() as connection:
        expected = dict(connection.execute(query).mappings().one())
    assert expected["default_asc606"] == 20260912
    command.downgrade(alembic_config(), "0161")
    with test_database.owner_engine.begin() as connection:
        assert dict(connection.execute(query).mappings().one()) == expected
        # Model a database seeded before replay_seed existed. Only this disposable test uses
        # the owner to remove the append-only row; upgrade itself needs no disabled trigger.
        connection.execute(
            text(
                "ALTER TABLE erev.registry_parameter "
                "DISABLE TRIGGER tg_registry_parameter__immutable"
            )
        )
        connection.execute(
            text("DELETE FROM erev.registry_parameter WHERE code = 'platform.replay_seed'")
        )
        connection.execute(
            text(
                "ALTER TABLE erev.registry_parameter "
                "ENABLE TRIGGER tg_registry_parameter__immutable"
            )
        )
    command.upgrade(alembic_config(), "head")
    with test_database.owner_engine.connect() as connection:
        assert dict(connection.execute(query).mappings().one()) == expected
    command.downgrade(alembic_config(), "0161")
    command.upgrade(alembic_config(), "head")
    with test_database.owner_engine.connect() as connection:
        assert dict(connection.execute(query).mappings().one()) == expected
