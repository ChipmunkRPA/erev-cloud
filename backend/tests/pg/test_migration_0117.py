"""Revision 0117 at the catalogue (04 rev 1.241 T-CON-13 Keys; PRD rev 1.168 SM-04, ERR-93; the
supervisor's rulings of 2026-10-01; item EST-ONE-OPEN-VERSION-1). PostgreSQL-bound; every test
writes the rows of a tenant of its own.

``ux_estimate_version__open`` — at most one version of an element is DRAFT or SUBMITTED. The
commands refuse a second one by name (``estimates._refuse_open``, PRD ERR-93); the index holds the
same for a writer below them. The rows are written along the DB-03 pairs of SM-04:

1. A second version is refused where it would become open — by its INSERT, and by the UPDATE
   that returns a REJECTED or WITHDRAWN version to DRAFT — and is stored beside a version in
   every status that is not open; a version of another element is not counted.
2. The index is not built over two open versions, which is how the upgrade fails on a database
   that holds them; once one of the two is discarded (DRAFT to VOIDED) it is built.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import estimate, estimate_version
from sqlalchemy import exc, insert, select, text, update
from support.db import TestDatabase
from support.principals import member
from support.rows import estimate_values, estimate_version_values, insert_contract_rows

pytestmark = pytest.mark.pg

INDEX = "ux_estimate_version__open"
OPEN = ["DRAFT", "SUBMITTED"]

_KEY = text(
    "SELECT a.attname::text FROM pg_index x "
    "JOIN pg_class i ON i.oid = x.indexrelid "
    "JOIN pg_namespace n ON n.oid = i.relnamespace AND n.nspname = 'erev' "
    "CROSS JOIN LATERAL unnest(x.indkey::int2[]) WITH ORDINALITY AS k (attnum, position) "
    "JOIN pg_attribute a ON a.attrelid = x.indrelid AND a.attnum = k.attnum "
    "WHERE i.relname = :index ORDER BY k.position"
)
_DEFINITION = text("SELECT pg_get_indexdef(('erev.' || :index)::regclass)")
_PRESENT = text("SELECT to_regclass('erev.' || :index) IS NOT NULL")


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _refused(session: Any, statement: Any) -> Any:
    """The database error of ``statement``, run in a savepoint that is rolled back."""
    savepoint = session.begin_nested()
    with pytest.raises(exc.DBAPIError) as refused:
        session.execute(statement)
    savepoint.rollback()
    return refused.value.orig


def _moved(row: dict[str, Any], status: str) -> Any:
    return update(estimate_version).where(estimate_version.c.id == row["id"]).values(status=status)


def test_0117_one_version_of_an_element_is_open(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    with test_database.owner_engine.connect() as connection:
        key = [str(name) for name in connection.execute(_KEY, {"index": INDEX}).scalars()]
        definition = str(connection.execute(_DEFINITION, {"index": INDEX}).scalar_one())
    assert key == ["tenant_id", "estimate_id"]  # both uuid: a policy lets them bound a scan
    head, _, predicate = definition.partition(" WHERE ")
    assert head.startswith(f"CREATE UNIQUE INDEX {INDEX} ON erev.estimate_version "), definition
    assert re.findall(r"'([A-Z_]+)'", predicate) == OPEN, definition

    tenant_id = member(keyring, clock).tenant_id
    with tenant_session(_context(tenant_id)) as session:
        chain = insert_contract_rows(session, tenant_id)
        element = estimate_values(tenant_id, contract_id=chain.contract_id)
        other = estimate_values(tenant_id, contract_id=chain.contract_id)
        session.execute(insert(estimate), [element, other])

        def version(number: int, of: dict[str, Any] = element) -> dict[str, Any]:
            return estimate_version_values(tenant_id, estimate_id=of["id"], version_no=number)

        def stored(row: dict[str, Any]) -> dict[str, Any]:
            session.execute(insert(estimate_version).values(**row))
            return row

        def second(statement: Any) -> None:
            assert _refused(session, statement).diag.constraint_name == INDEX

        # a draft is open, and so is a version that waits for its approval
        first = stored(version(1))
        second(insert(estimate_version).values(**version(2)))
        stored(version(1, other))  # a version of another element is not counted
        session.execute(_moved(first, "SUBMITTED"))
        second(insert(estimate_version).values(**version(2)))

        # REJECTED is not open: a new version is stored beside it — and it does not come back
        # to a draft beside that one
        session.execute(_moved(first, "REJECTED"))
        later = stored(version(2))
        second(_moved(first, "DRAFT"))

        # WITHDRAWN likewise
        session.execute(_moved(later, "SUBMITTED"))
        second(_moved(first, "DRAFT"))
        session.execute(_moved(later, "WITHDRAWN"))
        session.execute(_moved(first, "DRAFT"))
        second(_moved(later, "DRAFT"))

        # VOIDED, APPROVED and SUPERSEDED are not open
        session.execute(_moved(first, "VOIDED"))
        for status in ("DRAFT", "SUBMITTED", "APPROVED"):
            session.execute(_moved(later, status))
        third = stored(version(3))
        for status in ("SUBMITTED", "APPROVED"):
            session.execute(_moved(third, status))
        session.execute(_moved(later, "SUPERSEDED"))
        stored(version(4))
        second(insert(estimate_version).values(**version(5)))
        found = session.execute(
            select(estimate_version.c.version_no, estimate_version.c.status)
            .where(estimate_version.c.estimate_id == element["id"])
            .order_by(estimate_version.c.version_no)
        )
        assert [
            (int(row.version_no), str(getattr(row.status, "value", row.status))) for row in found
        ] == [
            (1, "VOIDED"),
            (2, "SUPERSEDED"),
            (3, "APPROVED"),
            (4, "DRAFT"),
        ]
        session.rollback()


def test_0117_the_index_is_not_built_over_two_open_versions(
    test_database: TestDatabase, keyring: KeyRing, clock: FrozenClock
) -> None:
    owner = test_database.owner_engine
    tenant_id = member(keyring, clock).tenant_id
    with owner.connect() as connection:
        definition = str(connection.execute(_DEFINITION, {"index": INDEX}).scalar_one())
    with tenant_session(_context(tenant_id)) as session:
        chain = insert_contract_rows(session, tenant_id)
        element = estimate_values(tenant_id, contract_id=chain.contract_id)
        session.execute(insert(estimate).values(**element))
        first = estimate_version_values(tenant_id, estimate_id=element["id"], version_no=1)
        session.execute(insert(estimate_version).values(**first))
    extra = estimate_version_values(tenant_id, estimate_id=element["id"], version_no=2)
    try:
        with owner.begin() as connection:
            connection.exec_driver_sql(f"DROP INDEX erev.{INDEX}")
        # the state revision 0117 may meet: two drafts of one element, written before it
        with tenant_session(_context(tenant_id)) as session:
            session.execute(insert(estimate_version).values(**extra))
        with pytest.raises(exc.DBAPIError) as refused, owner.begin() as connection:
            connection.exec_driver_sql(definition)
        assert refused.value.orig.sqlstate == "23505", refused.value.orig  # unique_violation
        with owner.connect() as connection:
            assert connection.execute(_PRESENT, {"index": INDEX}).scalar_one() is False
    finally:
        # what the operator does: one of the two is discarded — and the index is built
        with tenant_session(_context(tenant_id)) as session:
            session.execute(_moved(extra, "VOIDED"))
        with owner.begin() as connection:
            if not connection.execute(_PRESENT, {"index": INDEX}).scalar_one():
                connection.exec_driver_sql(definition)  # as the catalogue printed it
    with owner.connect() as connection:
        assert connection.execute(_DEFINITION, {"index": INDEX}).scalar_one() == definition
