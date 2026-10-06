"""Global catalogues T-REF-08 and T-PLT-11 (04 §14.2; DG-MIG-07; BUILD_SPEC FND-7)."""

from __future__ import annotations

import pytest
from erev_api.auth.permissions import CATALOGUE
from erev_api.db.session import identity_session
from erev_engine.currencies import ISO_4217
from sqlalchemy import Connection, exc, text
from support.db import TestDatabase

pytestmark = pytest.mark.pg


def _sqlstate(connection: Connection, statement: str) -> str | None:
    savepoint = connection.begin_nested()
    with pytest.raises(exc.DBAPIError) as excinfo:
        connection.exec_driver_sql(statement)
    savepoint.rollback()
    return getattr(excinfo.value.orig, "sqlstate", None)


def _privileges(connection: Connection, table: str) -> dict[str, bool]:
    return {
        privilege: connection.execute(
            text("SELECT has_table_privilege('erev_app', :table, :privilege)"),
            {"table": table, "privilege": privilege},
        ).scalar_one()
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
    }


def test_currency_seeded(test_database: TestDatabase) -> None:
    with identity_session(request_id="tests-currency") as session:
        connection = session.connection()
        rows = connection.execute(
            text(
                "SELECT code, numeric_code, name, minor_unit, is_active FROM erev.currency "
                "ORDER BY code"
            )
        ).all()
        assert len(rows) == len(ISO_4217)
        assert [tuple(row) for row in rows] == [
            (c.code, c.numeric_code, c.name, c.minor_unit, True) for c in ISO_4217.values()
        ]
        minor_unit = connection.execute(
            text("SELECT minor_unit FROM erev.currency WHERE code = 'BHD'")
        ).scalar_one()
        assert minor_unit == 3
        insert = (
            "INSERT INTO erev.currency (code, numeric_code, name, minor_unit) "
            "VALUES ('XTS', '963', 'Probe', 2)"
        )
        assert _sqlstate(connection, insert) == "42501"
        assert _privileges(connection, "erev.currency") == {
            "SELECT": True,
            "INSERT": False,
            "UPDATE": False,
            "DELETE": False,
            "TRUNCATE": False,
        }


def test_permission_seeded(test_database: TestDatabase) -> None:
    with identity_session(request_id="tests-permission") as session:
        connection = session.connection()
        rows = connection.execute(
            text(
                "SELECT code, area, description, is_approval, is_access_admin, requires_mfa "
                "FROM erev.permission"
            )
        ).all()
        assert len(rows) == 52
        assert sorted(tuple(row) for row in rows) == sorted(
            (p.code, p.area, p.description, p.is_approval, p.is_access_admin, p.requires_mfa)
            for p in CATALOGUE
        )
        mfa = dict(
            connection.execute(
                text(
                    "SELECT code, requires_mfa FROM erev.permission "
                    "WHERE code IN ('period.lock', 'contract.read')"
                )
            ).all()
        )
        assert mfa == {"period.lock": True, "contract.read": False}
        update = "UPDATE erev.permission SET requires_mfa = false WHERE code = 'period.lock'"
        assert _sqlstate(connection, update) == "42501"
        assert _privileges(connection, "erev.permission")["SELECT"] is True
        assert _privileges(connection, "erev.permission")["INSERT"] is False
