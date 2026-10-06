"""Row-builder shape guards for ``tests/support/rows.py`` (DG-TST-20; CTL-036 isolation probes),
CPU only — the DB-bound isolation run is the integrated batch's.

``_insert_visible`` inserts a dependent row in a savepoint and returns ``row["id"]``, so every table
it is handed must carry an ``id`` column; a keyless table (``subledger_posting_seal``, keyed by
``subledger_posting_id``) must be inserted plainly or through a tolerant helper that returns
nothing. Fail-first on the merge 2898db9b: ``subledger_line_event_row`` handed the seal to
``_insert_visible`` (integrated batch on main 0cb36c14, ``test_ctl_036_cross_tenant_isolation
[subledger_line_event]``: ``KeyError: 'id'`` at ``_insert_visible``).
"""

from __future__ import annotations

import ast
from pathlib import Path

from erev_api.db import tables

ROWS = Path(__file__).resolve().parents[1] / "support" / "rows.py"


def _table_names() -> dict[str, set[str]]:
    """Table variable name (as imported in rows.py) -> its column names, from the 04 metadata."""
    found: dict[str, set[str]] = {}
    for table in tables.metadata.sorted_tables:
        found[table.name] = {column.name for column in table.columns}
    return found


def test_insert_visible_is_only_handed_tables_with_an_id_column() -> None:
    columns = _table_names()
    module = ast.parse(ROWS.read_text(encoding="utf-8"))
    aliases = {
        alias.asname or alias.name: alias.name
        for node in ast.walk(module)
        if isinstance(node, ast.ImportFrom) and node.module == "erev_api.db.tables"
        for alias in node.names
    }
    handed: list[tuple[int, str]] = []
    for node in ast.walk(module):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_insert_visible"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Name)
        ):
            handed.append((node.lineno, aliases.get(node.args[1].id, node.args[1].id)))
    assert handed, "no _insert_visible call found in rows.py"
    keyless = sorted(
        {(line, name) for line, name in handed if name in columns and "id" not in columns[name]}
    )
    assert keyless == [], f"_insert_visible handed keyless tables (returns row['id']): {keyless}"
