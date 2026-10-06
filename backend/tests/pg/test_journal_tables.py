"""Journal table checks (04 T-SL-06, T-SL-09; BUILD_SPEC CLO-1)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import journal_line, journal_run
from sqlalchemy import Executable, exc, func, insert, select
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import insert_journal_rows, journal_line_values, journal_run_values

pytestmark = pytest.mark.pg

CHECK_VIOLATION = "23514"


def _refused(session: Session, statement: Executable) -> tuple[str | None, str | None]:
    """SQLSTATE and constraint name of a statement that must fail; only its savepoint rolls back."""
    savepoint = session.begin_nested()
    with pytest.raises(exc.DBAPIError) as excinfo:
        session.execute(statement)
    savepoint.rollback()
    orig = excinfo.value.orig
    diag = getattr(orig, "diag", None)
    return getattr(orig, "sqlstate", None), getattr(diag, "constraint_name", None)


def test_check_constraints(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # 04 T-SL-06 and T-SL-09 (CLO-1): a run never summarises the LEGACY book, a DELTA run names the
    # LEGACY book as its delta book and only a DELTA run names one, and a journal line carries a
    # debit or a credit in each currency, never both.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        rows = insert_journal_rows(session, tenant_id)
        parts = rows.parts
        legacy = journal_run_values(tenant_id, parts=parts, book_code="LEGACY")
        assert _refused(session, insert(journal_run).values(**legacy)) == (
            CHECK_VIOLATION,
            "ck_journal_run__book_code",
        )
        undeclared = journal_run_values(tenant_id, parts=parts, mode="DELTA")
        assert _refused(session, insert(journal_run).values(**undeclared)) == (
            CHECK_VIOLATION,
            "ck_journal_run__delta_book",
        )
        gross = journal_run_values(tenant_id, parts=parts, delta_book_code="LEGACY")
        assert _refused(session, insert(journal_run).values(**gross)) == (
            CHECK_VIOLATION,
            "ck_journal_run__delta_book",
        )
        entry_id, batch_id = rows.entries[0]["id"], rows.batch["id"]
        both = journal_line_values(
            tenant_id,
            parts=parts,
            entry_id=entry_id,
            batch_id=batch_id,
            line_no=3,
            debit=Decimal("1.00"),
            credit=Decimal("1.00"),
            credit_functional=Decimal("0"),
        )
        assert _refused(session, insert(journal_line).values(**both)) == (
            CHECK_VIOLATION,
            "ck_journal_line__txn_amounts",
        )
        # A DELTA run against the LEGACY book and a one-sided line are accepted.
        delta = journal_run_values(tenant_id, parts=parts, mode="DELTA", delta_book_code="LEGACY")
        session.execute(insert(journal_run).values(**delta))
        one_sided = journal_line_values(
            tenant_id, parts=parts, entry_id=entry_id, batch_id=batch_id, line_no=3
        )
        session.execute(insert(journal_line).values(**one_sided))
    with tenant_session(context, read_only=True) as session:
        runs = session.execute(select(func.count()).select_from(journal_run)).scalar_one()
        lines = session.execute(select(func.count()).select_from(journal_line)).scalar_one()
    assert (runs, lines) == (2, 3)
