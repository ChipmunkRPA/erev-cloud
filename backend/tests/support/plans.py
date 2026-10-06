"""Plans of the application's reads as PostgreSQL makes them for ``erev_app`` under row-level
security (dev-guide DG-KRN-DB-10; 04 §1.4 "Index conditions under a policy", rev 1.181).

Under a policy a condition bounds an index scan only when its operator is leakproof, and a read
can look indexed in its SQL while it reads every row of the tenant: only the plan shows it. A plan
test runs the product's own read once inside ``sent()``, takes the statement and the values the
application engine sent, and reads the plan PostgreSQL makes of exactly those in a tenant session
(``plan``). A statement builder's result is explained the same way.

A plan test asks what an index CAN take, not what is cheapest for a table of a few rows: the
planner's alternatives are switched off for the ``EXPLAIN`` (``FORCED``), and a condition the
policy keeps out of an index shows as ``Filter`` however the plan is forced. Where two indexes
could serve a read the planner still tells them apart by cost, and on a table of one page every
index costs the same: such a test first writes ``ROWS`` rows for its tenant and analyses the table.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

from erev_api.db.lint import catalogue_connection
from erev_api.db.session import DbContext, app_engine, tenant_session
from sqlalchemy import Select, event, text
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ClauseElement, Executable
from support.db import TestDatabase

# Planner alternatives switched off while a plan is read.
FORCED = ("enable_seqscan", "enable_bitmapscan", "enable_hashjoin", "enable_mergejoin")
# Rows a test writes for its tenant where two indexes could serve its read.
ROWS = 2_000
type Sent = tuple[str, Any]  # a statement as the driver got it, and its parameters

_KEY = text(
    """
    SELECT a.attname::text
    FROM pg_index x
    JOIN pg_class i ON i.oid = x.indexrelid
    JOIN pg_namespace n ON n.oid = i.relnamespace AND n.nspname = 'erev'
    CROSS JOIN LATERAL unnest(x.indkey::int2[]) WITH ORDINALITY AS k (attnum, position)
    JOIN pg_attribute a ON a.attrelid = x.indrelid AND a.attnum = k.attnum
    WHERE i.relname = :index AND k.position <= x.indnkeyatts
    ORDER BY k.position
    """
)


class _Explain(Executable, ClauseElement):
    """``EXPLAIN (FORMAT JSON) <statement>``, executed with the statement's own parameters."""

    inherit_cache = False

    def __init__(self, statement: Select[Any]) -> None:
        self.statement = statement


@compiles(_Explain, "postgresql")
def _compile_explain(element: _Explain, compiler: Any, **kw: Any) -> str:
    return "EXPLAIN (FORMAT JSON) " + str(compiler.process(element.statement, **kw))


@contextmanager
def sent() -> Iterator[list[Sent]]:
    """Every statement the application engine sends while the block runs, with its values."""
    seen: list[Sent] = []

    def record(
        _connection: Any, _cursor: Any, statement: str, parameters: Any, _context: Any, _many: bool
    ) -> None:
        seen.append((statement, parameters))

    engine = app_engine()
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", record)


def reads(seen: list[Sent], table: str) -> list[Sent]:
    """The SELECTs among ``seen`` that read ``erev.<table>``, in the order they were sent."""
    name = re.compile(rf"\berev\.{table}\b")
    return [
        (statement, parameters)
        for statement, parameters in seen
        if statement.lstrip().upper().startswith(("SELECT", "WITH")) and name.search(statement)
    ]


def nodes(plan: Any) -> Iterator[dict[str, Any]]:
    """Every node of an ``EXPLAIN (FORMAT JSON)`` plan, parents before children."""
    yield plan
    for child in plan.get("Plans", ()):
        yield from nodes(child)


def plan(
    tenant_id: UUID, read: Sent | Select[Any], *, off: tuple[str, ...] = FORCED
) -> dict[str, Any]:
    """The plan PostgreSQL makes of ``read`` as the application runs it: ``erev_app`` under the
    tenant's row-level security, with the values the read binds. ``off`` are planner settings
    switched off for this one transaction."""
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        connection = session.connection()
        for setting in off:  # names a test module states, never a value from outside
            connection.exec_driver_sql(f"SET LOCAL {setting} = off")
        if isinstance(read, tuple):
            statement, parameters = read
            raw = connection.exec_driver_sql(
                "EXPLAIN (FORMAT JSON) " + statement, parameters
            ).scalar_one()
        else:
            raw = session.execute(_Explain(read)).scalar_one()
        session.rollback()
    document = json.loads(raw) if isinstance(raw, str) else raw
    found: dict[str, Any] = document[0]["Plan"]
    return found


def scan(found: dict[str, Any], table: str) -> dict[str, Any]:
    """The one scan of ``table`` in a plan."""
    (node,) = [node for node in nodes(found) if node.get("Relation Name") == table]
    return node


def bound_by(node: dict[str, Any], index: str, *columns: str) -> None:
    """``node`` is a scan of ``index`` that the tenant and ``columns`` BOUND: they are the
    leading columns of the index key, in that order, and each is in the INDEX CONDITION.

    The second half alone proves nothing. PostgreSQL also lists a condition on a column that
    stands behind an unbound one as an index condition — it is then compared entry by entry
    over everything the columns in front select, which is what the keys were before revision
    0112: ``idempotency_key = …`` was an "Index Cond" of ``(tenant_id, book_code,
    idempotency_key)`` and the scan still walked the tenant's whole key."""
    assert node["Node Type"] in ("Index Scan", "Index Only Scan"), node
    assert node["Index Name"] == index, node
    with catalogue_connection(request_id="tests-plans") as connection:
        key = [str(name) for name in connection.execute(_KEY, {"index": index}).scalars()]
    bound = ["tenant_id", *columns]
    assert key[: len(bound)] == bound, (index, key)
    condition = node.get("Index Cond", "")
    for column in bound:
        assert re.search(rf"\b{column} [=<>]", condition), (column, node)


def analyse(test_database: TestDatabase, *tables: str) -> None:
    """Statistics for ``tables``, as the owner: the planner tells two keys apart by them."""
    with test_database.owner_engine.begin() as connection:
        for table in tables:  # table names a test module states
            connection.exec_driver_sql(f"ANALYZE erev.{table}")
