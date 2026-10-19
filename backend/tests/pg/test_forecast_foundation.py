"""Forecast schema upgrade/downgrade and installed isolation/state guards."""

import pytest
from alembic import command
from erev_api.db.transitions import transition_trigger_sql
from sqlalchemy import text
from support.db import TestDatabase, alembic_config

pytestmark = pytest.mark.pg


def test_forecast_schema_round_trip(test_database: TestDatabase) -> None:
    with test_database.owner_engine.connect() as connection:
        for table in ("forecast_run", "deal_preview"):
            body = connection.execute(
                text("SELECT prosrc FROM pg_proc WHERE oid = to_regprocedure(:signature)"),
                {"signature": f"erev.tg_{table}__transition()"},
            ).scalar_one()
            assert body.strip() == transition_trigger_sql(table).strip()
        for table in ("scenario", "forecast_event_set", "forecast_run", "deal_preview"):
            assert connection.execute(
                text(
                    "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                    "WHERE oid = to_regclass(:name)"
                ),
                {"name": f"erev.{table}"},
            ).scalar_one()
    command.downgrade(alembic_config(), "0175")
    with test_database.owner_engine.connect() as connection:
        assert connection.execute(text("SELECT to_regclass('erev.scenario')")).scalar() is None
    command.upgrade(alembic_config(), "head")
