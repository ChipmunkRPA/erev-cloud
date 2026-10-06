"""Small SQLite fixtures for the migration API tests (DG-ARC-05 / DG-LAY-11: ``sqlite3`` is
imported only under ``backend/erev_api/domain/migration/``, ``scripts/build_fixtures.py`` and
``backend/tests/support/parity/``). WLD-F-35 ``not-a-legacy-db.sqlite`` (PRD J-20-ALT-2) is a SQLite
file WITHOUT ``Contract_Live``; the minimal legacy shape carries the table and nothing else.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

__all__ = ["sqlite_copy_with_cell", "sqlite_with_contract_live", "sqlite_without_contract_live"]


def sqlite_without_contract_live(path: Path) -> Path:
    """A real SQLite database with no ``Contract_Live`` table (WLD-F-35)."""
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE "Something_Else" (x TEXT)')
    return path


def sqlite_with_contract_live(path: Path) -> Path:
    """A real SQLite database whose only table is an empty ``Contract_Live``."""
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE "Contract_Live" ("Contract Unique Name" TEXT)')
    return path


def sqlite_copy_with_cell(
    source: Path, target: Path, *, table: str, column: str, rowid: int, value: object
) -> Path:
    """A copy of ``source`` with ONE cell changed — the negative-input fixtures of the migration
    tests (for example a REAL that renders as ``1e-19``: 19 fractional digits, beyond the API-C-06
    bound of ``ExactMoneyIn``). The source is never modified (REQ-MIG-004)."""
    shutil.copyfile(source, target)
    with sqlite3.connect(target) as connection:
        # identifiers are the fixture's literal table / column names (no user input); the value
        # and rowid are bound parameters
        statement = f'UPDATE "{table}" SET "{column}" = ? WHERE rowid = ?'  # noqa: S608
        connection.execute(statement, (value, rowid))
    return target
