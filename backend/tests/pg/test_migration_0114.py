"""Revision 0114 at the catalogue (04 rev 1.210 T-CON-06, T-CON-12, T-CON-13; supervisor rulings
R-118 (e) and R-119 (e) and the supervisor's rulings of 2026-10-01; lane API-GAPS' finding F1).
PostgreSQL-bound; every test writes the rows of a tenant of its own.

1. ``ix_estimate__contract`` — the plan of the list read of ``GET /contracts/{id}/estimates`` as
   the application runs it: ``erev_app`` under the tenant's row-level security. Under a policy a
   read can look indexed in its SQL and still read every row of the tenant; only the plan shows
   it. With the index the scan is bound by the tenant and the contract; without it — the index is
   dropped and re-created from its catalogue definition around the second reading — the contract
   is a filter over everything the tenant holds. The planner's alternatives are switched off for
   the ``EXPLAIN``: the test asks what an index CAN take, and on a table of one page every index
   costs the same, so it first writes ``ESTIMATES`` rows over ``CONTRACTS`` contracts and
   analyses the table.
2. ``ux_modification__reference`` — a discarded draft (``VOIDED``, never applied) does not hold
   its reference; a voided row that carries an applied event holds it. No command produces the
   second state today (nothing moves an applied modification to ``VOIDED``); the rows are written
   along the DB-03 pairs.
3. The column grants — ``estimate_version.modification_id`` is written by the INSERT and has no
   UPDATE grant for ``erev_app``; ``modification.classification`` has one, and its check admits
   an object or NULL.
4. ``ix_estimate_version__modification`` — the read behind ``linked_estimate_versions`` of every
   modification answer (item MOD-LINKED-ESTIMATES-1): its equality proves the partial index's
   predicate and bounds the scan by the tenant and the modification.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import pytest
from erev_api.api.lists import ListParams, paginate
from erev_api.api.v1.estimates import ESTIMATE_LIST
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, app_engine, tenant_session
from erev_api.db.tables import (
    combination_group,
    contract,
    contract_event,
    estimate,
    estimate_version,
    modification,
)
from erev_api.domain.contracts import estimates, modifications
from sqlalchemy import event, exc, insert, text, update
from support.db import TestDatabase
from support.principals import member
from support.rows import (
    combination_group_values,
    contract_event_values,
    contract_values,
    estimate_values,
    estimate_version_values,
    insert_contract_rows,
    modification_values,
)

pytestmark = pytest.mark.pg

INDEX = "ix_estimate__contract"
LINK_INDEX = "ix_estimate_version__modification"
# Planner alternatives switched off while a plan is read.
FORCED = ("enable_seqscan", "enable_bitmapscan")
CONTRACTS = 400
ESTIMATES = 2_000  # five elements a contract
type Sent = tuple[str, Any]  # a statement as the driver got it, and its parameters

_KEY = text(
    "SELECT a.attname::text FROM pg_index x "
    "JOIN pg_class i ON i.oid = x.indexrelid "
    "JOIN pg_namespace n ON n.oid = i.relnamespace AND n.nspname = 'erev' "
    "CROSS JOIN LATERAL unnest(x.indkey::int2[]) WITH ORDINALITY AS k (attnum, position) "
    "JOIN pg_attribute a ON a.attrelid = x.indrelid AND a.attnum = k.attnum "
    "WHERE i.relname = :index ORDER BY k.position"
)
_DEFINITION = text("SELECT pg_get_indexdef(('erev.' || :index)::regclass)")
_UPDATE_GRANT = text(
    "SELECT has_column_privilege('erev_app', ('erev.' || :table)::regclass, :column, 'UPDATE')"
)


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@contextmanager
def _sent() -> Iterator[list[Sent]]:
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


def _scan(tenant_id: UUID, read: Sent, table: str) -> dict[str, Any]:
    """The scan of ``table`` in the plan PostgreSQL makes of ``read`` for ``erev_app`` under the
    tenant's policy, with the values the read bound."""
    statement, parameters = read
    with tenant_session(_context(tenant_id)) as session:
        connection = session.connection()
        for setting in FORCED:
            connection.exec_driver_sql(f"SET LOCAL {setting} = off")
        raw = connection.exec_driver_sql(
            "EXPLAIN (FORMAT JSON) " + statement, parameters
        ).scalar_one()
        session.rollback()
    document = json.loads(raw) if isinstance(raw, str) else raw

    def nodes(plan: dict[str, Any]) -> Iterator[dict[str, Any]]:
        yield plan
        for child in plan.get("Plans", ()):
            yield from nodes(child)

    (found,) = [node for node in nodes(document[0]["Plan"]) if node.get("Relation Name") == table]
    return found


def test_0114_a_contracts_estimates_are_read_through_their_index(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    tenant_id = member(keyring, clock).tenant_id
    owner = test_database.owner_engine
    with tenant_session(_context(tenant_id)) as session:
        first = insert_contract_rows(session, tenant_id)
        groups = [combination_group_values(tenant_id) for _ in range(CONTRACTS - 1)]
        session.execute(insert(combination_group), groups)
        contracts = [
            contract_values(
                tenant_id,
                customer_id=first.customer_id,
                contracting_entity_id=first.entity_id,
                combination_group_id=group["id"],
            )
            for group in groups
        ]
        session.execute(insert(contract), contracts)
        contract_ids = [first.contract_id, *(row["id"] for row in contracts)]
        session.execute(
            insert(estimate),
            [
                estimate_values(tenant_id, contract_id=contract_id)
                for contract_id in contract_ids
                for _ in range(ESTIMATES // CONTRACTS)
            ],
        )
    with owner.begin() as connection:
        connection.exec_driver_sql("ANALYZE erev.estimate")
        key = [str(name) for name in connection.execute(_KEY, {"index": INDEX}).scalars()]
        definition = str(connection.execute(_DEFINITION, {"index": INDEX}).scalar_one())
    assert key == ["tenant_id", "contract_id"]  # the columns the read binds LEAD the key

    # the product's own read, once: the statement and the values the application engine sent
    wanted = contract_ids[CONTRACTS // 2]
    params = ListParams(limit=50, cursor=None, sort=None, q=None, count=False, filters={})
    with _sent() as seen, tenant_session(_context(tenant_id)) as session:
        page = paginate(
            session, estimates.estimates_statement(contract_id=wanted), ESTIMATE_LIST, params
        )
        assert len(page.items) == ESTIMATES // CONTRACTS
    (read,) = [
        (statement, parameters)
        for statement, parameters in seen
        if statement.lstrip().upper().startswith("SELECT")
        and re.search(r"\berev\.estimate\b", statement)
    ]

    found = _scan(tenant_id, read, "estimate")
    assert found["Node Type"] in ("Index Scan", "Index Only Scan"), found
    assert found["Index Name"] == INDEX, found
    for column in key:
        assert re.search(rf"\b{column} =", found["Index Cond"]), (column, found)

    # the same read without the index: the contract bounds nothing
    try:
        with owner.begin() as connection:
            connection.exec_driver_sql(f"DROP INDEX erev.{INDEX}")
        before = _scan(tenant_id, read, "estimate")
    finally:
        with owner.begin() as connection:
            connection.exec_driver_sql(definition)  # as the catalogue printed it
    assert before.get("Index Name") != INDEX, before
    assert "contract_id" not in before.get("Index Cond", ""), before
    assert "contract_id" in before["Filter"], before
    with owner.connect() as connection:
        assert connection.execute(_DEFINITION, {"index": INDEX}).scalar_one() == definition


def _refused(session: Any, statement: Any) -> Any:
    """The database error of ``statement``, run in a savepoint that is rolled back."""
    savepoint = session.begin_nested()
    with pytest.raises(exc.DBAPIError) as refused:
        session.execute(statement)
    savepoint.rollback()
    return refused.value.orig


def test_0114_a_discarded_draft_frees_its_reference(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    tenant_id = member(keyring, clock).tenant_id
    with tenant_session(_context(tenant_id)) as session:
        chain = insert_contract_rows(session, tenant_id, head_stream_version=1)
        applying = contract_event_values(
            tenant_id,
            contract_id=chain.contract_id,
            contracting_entity_id=chain.entity_id,
            stream_version=1,
        )
        session.execute(insert(contract_event).values(**applying))

        def draft() -> dict[str, Any]:
            return modification_values(
                tenant_id,
                contract_id=chain.contract_id,
                contracting_entity_id=chain.entity_id,
                reference="CR-2026-014",
            )

        def move(row: dict[str, Any], status: str, **values: Any) -> None:
            session.execute(
                update(modification)
                .where(modification.c.id == row["id"])
                .values(status=status, **values)
            )

        first = draft()
        session.execute(insert(modification).values(**first))
        taken = _refused(session, insert(modification).values(**draft()))
        assert taken.diag.constraint_name == "ux_modification__reference"

        move(first, "VOIDED")  # a discarded draft: never applied
        second = draft()
        session.execute(insert(modification).values(**second))  # the reference is free again
        taken = _refused(session, insert(modification).values(**draft()))
        assert taken.diag.constraint_name == "ux_modification__reference"  # … and held as before

        # an applied modification that is voided keeps its reference
        move(second, "SUBMITTED")
        move(second, "APPROVED")
        move(second, "APPLIED", applied_event_id=applying["id"])
        move(second, "VOIDED")
        taken = _refused(session, insert(modification).values(**draft()))
        assert taken.diag.constraint_name == "ux_modification__reference"
        session.rollback()


def test_0114_the_link_of_an_estimate_version_is_written_once(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    with test_database.owner_engine.connect() as connection:
        granted = {
            (table, column): bool(
                connection.execute(_UPDATE_GRANT, {"table": table, "column": column}).scalar_one()
            )
            for table, column in (
                ("estimate_version", "modification_id"),
                ("estimate_version", "rationale"),
                ("modification", "classification"),
            )
        }
    assert granted == {
        ("estimate_version", "modification_id"): False,
        ("estimate_version", "rationale"): True,
        ("modification", "classification"): True,
    }
    tenant_id = member(keyring, clock).tenant_id
    with tenant_session(_context(tenant_id)) as session:
        chain = insert_contract_rows(session, tenant_id)
        change = modification_values(
            tenant_id, contract_id=chain.contract_id, contracting_entity_id=chain.entity_id
        )
        session.execute(insert(modification).values(**change))
        element = estimate_values(tenant_id, contract_id=chain.contract_id)
        session.execute(insert(estimate).values(**element))
        version = estimate_version_values(
            tenant_id, estimate_id=element["id"], modification_id=change["id"]
        )
        session.execute(insert(estimate_version).values(**version))  # the INSERT writes the link

        # a DRAFT version is editable (DB-03 lets every column of a draft change): the grant alone
        # keeps the link from being rewritten
        rewritten = _refused(
            session,
            update(estimate_version)
            .where(estimate_version.c.id == version["id"])
            .values(modification_id=None),
        )
        assert rewritten.sqlstate == "42501", rewritten  # insufficient_privilege
        session.execute(
            update(estimate_version)
            .where(estimate_version.c.id == version["id"])
            .values(rationale="Edited while a draft.")
        )

        # T-CON-06 classification: written while DRAFT, an object or NULL
        for value in ({"proposal": {}}, None):
            session.execute(
                update(modification)
                .where(modification.c.id == change["id"])
                .values(classification=value)
            )
        shaped = _refused(
            session,
            update(modification)
            .where(modification.c.id == change["id"])
            .values(classification=text("'[]'::jsonb")),
        )
        assert shaped.diag.constraint_name == "ck_modification__classification"
        session.rollback()


def test_0114_the_versions_of_a_modification_are_read_through_their_index(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    tenant_id = member(keyring, clock).tenant_id
    linked_each = ESTIMATES // CONTRACTS
    with tenant_session(_context(tenant_id)) as session:
        chain = insert_contract_rows(session, tenant_id)
        changes = [
            modification_values(
                tenant_id, contract_id=chain.contract_id, contracting_entity_id=chain.entity_id
            )
            for _ in range(CONTRACTS)
        ]
        session.execute(insert(modification), changes)
        element = estimate_values(tenant_id, contract_id=chain.contract_id)
        session.execute(insert(estimate).values(**element))
        # One version of an element is open at a time (``ux_estimate_version__open``, revision
        # 0117): the many versions of this one element are discarded drafts. The reader and its
        # index know no status.
        session.execute(
            insert(estimate_version),
            [
                estimate_version_values(
                    tenant_id,
                    estimate_id=element["id"],
                    version_no=number * linked_each + offset + 1,
                    modification_id=change["id"],
                    status="VOIDED",
                )
                for number, change in enumerate(changes)
                for offset in range(linked_each)
            ],
        )
    with test_database.owner_engine.begin() as connection:
        connection.exec_driver_sql("ANALYZE erev.estimate_version")
        key = [str(name) for name in connection.execute(_KEY, {"index": LINK_INDEX}).scalars()]
    assert key == ["tenant_id", "modification_id"]

    wanted = changes[CONTRACTS // 2]["id"]
    with _sent() as seen, tenant_session(_context(tenant_id)) as session:
        found = modifications.linked_estimate_versions(session, [wanted])
        assert [row["modification_id"] for row in found] == [wanted] * linked_each
    (read,) = [
        (statement, parameters)
        for statement, parameters in seen
        if re.search(r"\berev\.estimate_version\b", statement)
    ]
    node = _scan(tenant_id, read, "estimate_version")
    assert node["Node Type"] in ("Index Scan", "Index Only Scan"), node
    assert node["Index Name"] == LINK_INDEX, node
    for column in key:
        assert re.search(rf"\b{column} =", node["Index Cond"]), (column, node)
