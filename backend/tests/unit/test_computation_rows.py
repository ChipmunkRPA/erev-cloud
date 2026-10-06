"""``computation._insert_rows``: every row of a version is stored with the columns it names
(item CTR-BALANCE-ROWS-1; supervisor ruling R-114 (g); 04 T-CON-09).

One INSERT of several rows takes its columns from the first row (SQLAlchemy ``executemany``): a
later row that names fewer columns is refused, and a later row that names more loses them without
a word — the column is stored with the table's default. The engine names a ``_functional`` balance
only where it measures one, so the T-CON-09 rows of two contracting entities with different
functional currencies differ in columns. The database witness of the refused order is
``tests/domain/contracts/test_balance_rows_db.py``; these tests hold both orders without a
database (DG-ARC-05).
"""

from __future__ import annotations

import ast
import inspect
from decimal import Decimal
from typing import Any, cast

import pytest
from erev_api.db.tables import contract_version_balance
from erev_api.domain.contracts import computation
from sqlalchemy.orm import Session
from sqlalchemy.sql.dml import Insert

# Two entities of one version: at rate 1 the engine names the functional return asset, for the
# entity whose books are in another currency it names none.
AT_RATE_ONE = {
    "entity_id": "AVM-UK",
    "contract_asset_txn": Decimal("27450.00"),
    "return_asset_txn": Decimal("120.00"),
    "return_asset_functional": Decimal("120.00"),
}
REMEASURED = {
    "entity_id": "AVM-US",
    "contract_asset_txn": Decimal("0.00"),
    "return_asset_txn": Decimal("0.00"),
}


class Recording:
    """A session that keeps what one ``execute`` call carries: the table and its rows."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, list[dict[str, Any]]]] = []

    def execute(self, statement: Insert, rows: list[dict[str, Any]]) -> None:
        self.statements.append((statement.table.name, [dict(row) for row in rows]))


def sent(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    session = Recording()
    computation._insert_rows(cast(Session, session), contract_version_balance, rows)
    assert {name for name, _ in session.statements} <= {"contract_version_balance"}
    return [carried for _, carried in session.statements]


@pytest.mark.parametrize(
    "rows",
    [
        [AT_RATE_ONE, REMEASURED],  # as built: refused, the computation stored FAILED
        [REMEASURED, AT_RATE_ONE],  # as built: stored, the functional return asset lost
    ],
    ids=["the-row-with-more-columns-first", "the-row-with-fewer-columns-first"],
)
def test_every_row_is_sent_with_the_columns_it_names(rows: list[dict[str, Any]]) -> None:
    statements = sent(rows)
    # nothing is dropped, added or reordered
    assert [row for carried in statements for row in carried] == rows
    # and no statement carries rows of two column sets: its columns are its first row's
    for carried in statements:
        assert {tuple(sorted(row)) for row in carried} == {tuple(sorted(carried[0]))}


def test_rows_of_one_column_set_stay_one_statement() -> None:
    """The usual case — one entity, or entities of one functional currency — is one INSERT as
    before; a run of like rows after an unlike one is one statement too."""
    alike = [{**REMEASURED, "entity_id": code} for code in ("AVM-DE", "AVM-JP", "AVM-US")]
    assert sent(alike) == [alike]
    assert sent([AT_RATE_ONE, *alike]) == [[AT_RATE_ONE], alike]


def test_no_row_no_statement() -> None:
    assert sent([]) == []


def test_no_other_statement_of_the_module_carries_a_list_of_rows() -> None:
    """DG-CMD-09 (rev 1.157): in ``computation.py`` an INSERT with parameter rows is written in
    ``_insert_rows`` and nowhere else — ``session.execute(insert(table), rows)`` beside it would
    take its columns from the first row again."""
    found = [
        function.name
        for function in ast.walk(ast.parse(inspect.getsource(computation)))
        if isinstance(function, ast.FunctionDef)
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
        and len(node.args) > 1
        and isinstance(node.args[0], ast.Call)
        and getattr(node.args[0].func, "id", None) == "insert"
    ]
    assert found == ["_insert_rows"]
