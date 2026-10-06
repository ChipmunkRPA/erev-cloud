"""DG-TST-10 rev 1.269 (register index 249, TEST-ORDER-DEPENDENCIES-1): the value of the session
fixture keeps no engine. ``TestDatabase.app_engine`` and ``owner_engine`` answer the engines of
the process's factories at each use, also after ``dispose_engines()`` made the factories build new
ones. CPU: an engine is built here and never connected (DG-TST-18); what a kept engine cost on
the database is witnessed in ``tests/pg/test_session_guards.py``."""

from __future__ import annotations

from erev_api.db import session as session_module
from support.clock import frozen_clock
from support.db import TestDatabase


def test_dg_tst_10_the_fixtures_value_answers_the_factories_engines() -> None:
    database = TestDatabase(clock=frozen_clock())
    first = (database.app_engine, database.owner_engine)
    assert first == (session_module.app_engine(), session_module.owner_engine())
    assert database.app_engine is first[0] and database.owner_engine is first[1]
    # what the CLI's switch of environment and the end of ``worker.main`` do
    session_module.dispose_engines()
    assert database.app_engine is session_module.app_engine()
    assert database.owner_engine is session_module.owner_engine()
    assert database.app_engine is not first[0]
    assert database.owner_engine is not first[1]
