"""DG-ARC-07 transition drift (dev-guide §6.8, DG-SM-04; 04 §14.1 DB-03; BUILD_SPEC PLF-4)."""

from __future__ import annotations

import re

import pytest
from erev_api.db.session import identity_session
from erev_api.db.transitions import TRANSITIONS, transition_trigger_sql
from sqlalchemy import text
from support.db import TestDatabase

pytestmark = pytest.mark.pg

_FUNCTION_SOURCE = text(
    "SELECT p.prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
    "WHERE n.nspname = 'erev' AND p.proname = :name"
)
_TRIGGER = text(
    "SELECT pg_get_triggerdef(t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'erev' AND c.relname = :table AND t.tgname = :name"
)


def test_dg_arc_07_installed_functions_match_generated(test_database: TestDatabase) -> None:
    with identity_session(request_id="tests-dg-arc-07") as session:
        for table in sorted(TRANSITIONS):
            name = f"tg_{table}__transition"
            source = session.execute(_FUNCTION_SOURCE, {"name": name}).scalar_one()
            assert source == transition_trigger_sql(table), table
            definition = session.execute(_TRIGGER, {"table": table, "name": name}).scalar_one()
            # pg_get_triggerdef omits the schema when erev is on the search path (TXN-03).
            assert re.fullmatch(
                rf"CREATE TRIGGER {name} BEFORE UPDATE ON (erev\.)?{table} "
                rf"FOR EACH ROW EXECUTE FUNCTION (erev\.)?{name}\(\)",
                definition,
            ), definition
