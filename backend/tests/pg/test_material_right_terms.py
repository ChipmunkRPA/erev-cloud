"""T-CON-14: persisted option terms are immutable and cannot cross ownership boundaries."""

from __future__ import annotations

import importlib
from decimal import Decimal

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db import migration_ops, new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import contract, estimate, material_right
from sqlalchemy import delete, insert, select, text, update
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import RowContext, estimate_values, material_right_row
from tests.pg.test_db_invariants import _fails
from tests.pg.test_immutability_and_grants import _owner_failure

pytestmark = pytest.mark.pg


def test_material_right_guards(committed_db: TestDatabase, keyring: KeyRing) -> None:
    tenant = tenant_id_of(tenant_factory(keyring=keyring))
    other_tenant = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant, user_id=None, entity_scope="*")) as session:
        row = material_right_row(RowContext(tenant, new_id()), session)
        other = material_right_row(RowContext(tenant, new_id()), session)
        for changes, message in (
            ({"contract_id": other["contract_id"]}, "obligation must belong"),
            ({"currency": "EUR"}, "currency must match"),
            ({"incremental_discount_ratio": Decimal("1.1")}, "ck_material_right__ratio"),
            ({"expected_purchase_amount": Decimal("-1")}, "ck_material_right__purchase"),
            ({"ssp_method": "DISCOUNT_X_LIKELIHOOD"}, "ck_material_right__discount_terms"),
        ):
            state, detail = _fails(session, insert(material_right).values(**(row | changes)))
            assert state == "23514" and message in detail
        invalid = estimate_values(tenant, contract_id=row["contract_id"])
        session.execute(insert(estimate).values(**invalid))
        state, detail = _fails(
            session,
            insert(material_right).values(**(row | {"likelihood_estimate_id": invalid["id"]})),
        )
        assert state == "23514" and "exercise kind" in detail
        foreign = estimate_values(
            tenant,
            contract_id=other["contract_id"],
            estimate_kind="EXERCISE_LIKELIHOOD",
            method="RATE",
            vc_element_type=None,
        )
        session.execute(insert(estimate).values(**foreign))
        state, detail = _fails(
            session,
            insert(material_right).values(**(row | {"likelihood_estimate_id": foreign["id"]})),
        )
        assert state == "23514" and "exercise kind" in detail
        valid = estimate_values(
            tenant,
            contract_id=row["contract_id"],
            estimate_kind="EXERCISE_LIKELIHOOD",
            method="RATE",
            vc_element_type=None,
        )
        session.execute(insert(estimate).values(**valid))
        terms = row | {
            "ssp_method": "DISCOUNT_X_LIKELIHOOD",
            "incremental_discount_ratio": Decimal("0.3"),
            "expected_purchase_amount": Decimal("50"),
            "likelihood_estimate_id": valid["id"],
        }
        session.execute(insert(material_right).values(**terms))
        assert (
            _fails(session, insert(material_right).values(**(terms | {"id": new_id()})))[0]
            == "23505"
        )
        assert _fails(session, update(material_right).values(expected_purchase_amount=60))[0] in {
            "42501",
            "P0001",
        }
        assert _fails(session, delete(material_right))[0] in {"42501", "P0001"}
        assert _fails(
            session, insert(material_right).values(**(other | {"tenant_id": other_tenant}))
        )[0] in {"42501", "23514"}
    with tenant_session(
        DbContext(tenant_id=other_tenant, user_id=None, entity_scope="*")
    ) as session:
        assert session.execute(select(material_right)).first() is None

    with committed_db.owner_engine.connect() as connection:
        connection.begin()
        try:
            connection.exec_driver_sql(
                "ALTER TABLE erev.material_right NO FORCE ROW LEVEL SECURITY"
            )
            for statement in (
                update(material_right).values(expected_purchase_amount=60),
                delete(material_right),
            ):
                assert "EREV-IMM-001" in _owner_failure(connection, statement)
            # Isolate the FK from the parent's event-projection guard; rollback restores both.
            connection.exec_driver_sql("ALTER TABLE erev.contract NO FORCE ROW LEVEL SECURITY")
            connection.exec_driver_sql("ALTER TABLE erev.contract DISABLE TRIGGER USER")
            message = _owner_failure(
                connection,
                update(contract)
                .where(contract.c.id == row["contract_id"])
                .values(transaction_currency="EUR"),
            )
            assert "fk_material_right__contract_currency" in message
        finally:
            connection.rollback()


def test_material_right_migration_round_trip(committed_db: TestDatabase) -> None:
    migration = importlib.import_module("erev_api.db.migrations.versions.0145_material_right_terms")
    with committed_db.owner_engine.connect() as connection:
        transaction = connection.begin()
        try:
            with migration_ops.bound_to(connection):
                migration.downgrade()
                assert connection.scalar(text("SELECT to_regclass('erev.material_right')")) is None
                assert connection.scalar(text("SELECT to_regtype('erev.option_type')")) is None
                migration.upgrade()
            assert connection.scalar(text("SELECT to_regclass('erev.material_right')")) is not None
            assert connection.scalar(text("SELECT to_regtype('erev.option_type')")) is not None
            assert (
                connection.scalar(text("SELECT to_regclass('erev.ix_material_right__contract')"))
                is not None
            )
        finally:
            transaction.rollback()
