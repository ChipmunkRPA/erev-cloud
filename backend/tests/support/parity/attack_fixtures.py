"""SQLite attack fixture for the SAR-42 upload tests (05 UPL-09; BUILD_SPEC SOP-8). ``sqlite3`` is
imported only here, under ``backend/tests/support/parity/`` (DG-ARC-05 / DG-LAY-11); the tests
open the file through ``erev_api.domain.migration.legacy_db.connect_read_only`` and never import
``sqlite3`` themselves.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

__all__ = ["TRIGGER_LOG", "row_count", "sqlite_with_triggers"]

TRIGGER_LOG = "Trigger_Log"


def sqlite_with_triggers(path: Path) -> Path:
    """A real legacy-shaped database (``Contract_Live`` present) with a trigger that logs every
    insert into ``Trigger_Log`` and a view over the live table (UPL-09 fixture)."""
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE "Contract_Live" ("Contract Unique Name" TEXT);
            CREATE TABLE "Trigger_Log" (fired TEXT NOT NULL);
            CREATE TRIGGER "Fire_On_Insert" AFTER INSERT ON "Contract_Live"
            BEGIN INSERT INTO "Trigger_Log" VALUES ('fired'); END;
            CREATE VIEW "Contract_View" AS SELECT "Contract Unique Name" FROM "Contract_Live";
            """
        )
    return path


def row_count(path: Path, table: str) -> int:
    """Rows of a fixture table, read with a plain connection (the fixture's own view of itself)."""
    with sqlite3.connect(path) as connection:
        # ``table`` is a fixture literal chosen by the test, never user input.
        (count,) = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()  # noqa: S608
    return int(count)
