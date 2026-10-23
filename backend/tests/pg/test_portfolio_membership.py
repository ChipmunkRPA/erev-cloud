"""Shared-estimate membership retains closed history and tenant ownership."""

import importlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import DBAPIError
from support.db import TestDatabase, fresh_head
from support.factories import tenant_factory, tenant_id_of
from support.rows import RowContext, contract_row

from erev_api.auth.keyring import KeyRing
from erev_api.db import migration_ops, new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import contract, portfolio, portfolio_member
from tests.pg.test_db_invariants import _fails

pytestmark = pytest.mark.pg


def test_portfolio_membership_retains_intervals_and_tenant_boundary(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    tenant = tenant_id_of(tenant_factory(keyring=keyring))
    other = tenant_id_of(tenant_factory(keyring=keyring))
    now = datetime(2026, 10, 23, tzinfo=UTC)
    with tenant_session(DbContext(tenant_id=tenant, user_id=None, entity_scope="*")) as session:
        c = contract_row(RowContext(tenant, new_id()), session)
        session.execute(insert(contract).values(**c))
        portfolio_id = new_id()
        session.execute(
            insert(portfolio).values(
                tenant_id=tenant,
                id=portfolio_id,
                code="SHARED",
                name="Shared estimates",
                created_by_kind="SYSTEM",
                updated_by_kind="SYSTEM",
            )
        )
        member = dict(
            tenant_id=tenant,
            id=new_id(),
            portfolio_id=portfolio_id,
            contract_id=c["id"],
            valid_from_known_at=now,
            created_by_kind="SYSTEM",
        )
        session.execute(insert(portfolio_member).values(**member))
        assert (
            "overlapping portfolio membership"
            in _fails(session, insert(portfolio_member).values(**(member | {"id": new_id()})))[1]
        )
        session.execute(
            update(portfolio_member)
            .where(portfolio_member.c.id == member["id"])
            .values(valid_to_known_at=now + timedelta(days=1))
        )
        assert (
            "only closing portfolio membership is allowed"
            in _fails(session, update(portfolio_member).values(valid_to_known_at=None))[1]
        )
        assert _fails(session, delete(portfolio_member))[0] in {"42501", "P0001"}
        assert (
            "overlapping portfolio membership"
            in _fails(
                session,
                insert(portfolio_member).values(
                    **(member | {"id": new_id(), "valid_from_known_at": now + timedelta(hours=1)})
                ),
            )[1]
        )
        session.execute(
            insert(portfolio_member).values(
                **(
                    member
                    | {
                        "id": new_id(),
                        "valid_from_known_at": now + timedelta(days=1),
                    }
                )
            )
        )
        assert len(session.execute(select(portfolio_member)).all()) == 2
        assert _fails(
            session,
            insert(portfolio_member).values(
                **(
                    member
                    | {
                        "id": new_id(),
                        "tenant_id": other,
                    }
                )
            ),
        )[0] in {"42501", "23503"}
        session.commit()
    with tenant_session(DbContext(tenant_id=other, user_id=None, entity_scope="*")) as session:
        assert session.execute(select(portfolio)).first() is None
        assert session.execute(select(portfolio_member)).first() is None

    migration = importlib.import_module("erev_api.db.migrations.versions.0341_portfolio_membership")
    with committed_db.owner_engine.connect() as connection:
        transaction = connection.begin()
        try:
            with migration_ops.bound_to(connection), connection.begin_nested():
                with pytest.raises(DBAPIError, match="Cannot remove populated portfolio"):
                    with connection.begin_nested():
                        migration.downgrade()
            assert connection.scalar(text("SELECT to_regclass('erev.portfolio')")) is not None
        finally:
            transaction.rollback()


def test_empty_portfolio_migration_round_trip(committed_db: TestDatabase) -> None:
    fresh_head()
    migration = importlib.import_module("erev_api.db.migrations.versions.0341_portfolio_membership")
    with committed_db.owner_engine.connect() as connection:
        transaction = connection.begin()
        try:
            with migration_ops.bound_to(connection):
                migration.downgrade()
                assert connection.scalar(text("SELECT to_regclass('erev.portfolio')")) is None
                migration.upgrade()
                assert (
                    connection.scalar(text("SELECT to_regclass('erev.portfolio_member')"))
                    is not None
                )
        finally:
            transaction.rollback()
