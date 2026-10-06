"""T-MIG-01 to T-MIG-03 database behaviour (BUILD_SPEC LMG-1; 04 §17 rev 1.35; §14.1 DB-01, DB-03;
PRD SM-12, BR-MIG-01; NC-16). Written in lane F-LMG slice T-MIG; NOT RUN on the lane (the databases
``erev_rv_l24_*`` are Ray-side) — lane record docs/reviews/loop/prod/F-LMG.md §16. Row-level
security of the three tables runs through ``test_rls_isolation.py``
``test_ctl_036_cross_tenant_isolation`` (the ``ROW_BUILDERS`` parametrisation) and the schema
round trip through ``test_migrations.py``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    file_object,
    migrated_legacy_row,
    migration_batch,
    migration_reconciliation_line,
)
from erev_api.enums import FilePurpose
from sqlalchemy import Executable, delete, exc, insert, update
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import (
    exception_item_values,
    file_object_values,
    migrated_legacy_row_values,
    migration_batch_values,
    migration_reconciliation_line_values,
)

pytestmark = pytest.mark.pg

CHECK_VIOLATION = "23514"
UNIQUE_VIOLATION = "23505"
INSUFFICIENT_PRIVILEGE = "42501"
RAISE_EXCEPTION = "P0001"


def _fails(session: Session, statement: Executable) -> tuple[str | None, str]:
    """SQLSTATE and PRIMARY message of a statement that must fail (``diag.message_primary``, as
    ``test_db_invariants._error`` reads it — never ``str(error)``, which the server extends with an
    environment-dependent ``CONTEXT: PL/pgSQL function … at RAISE`` trailer; T1's first database
    run of 0056 surfaced that); only its savepoint rolls back."""
    savepoint = session.begin_nested()
    with pytest.raises(exc.DBAPIError) as excinfo:
        session.execute(statement)
    savepoint.rollback()
    origin = excinfo.value.orig
    diag = getattr(origin, "diag", None)
    return getattr(origin, "sqlstate", None), str(getattr(diag, "message_primary", "") or "")


def _batch(session: Session, tenant_id: Any, **extra: Any) -> dict[str, Any]:
    file_row = file_object_values(tenant_id, purpose=FilePurpose.LEGACY_DATABASE)
    session.execute(insert(file_object).values(**file_row))
    row = migration_batch_values(tenant_id, source_file_id=file_row["id"], **extra)
    session.execute(insert(migration_batch).values(**row))
    return row


def test_db_03_migration_batch_transitions(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DB-03 along E-76 (PRD SM-12): the chain moves forward, any non-terminal status may FAIL or be
    # CANCELLED, a skipped step is refused, unlisted columns are not granted, terminal is terminal.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        row = _batch(session, tenant_id)

        def move(**values: Any) -> Executable:
            return update(migration_batch).where(migration_batch.c.id == row["id"]).values(**values)

        assert _fails(session, move(status="PROMOTED")) == (
            RAISE_EXCEPTION,
            "EREV-TRN-001: status of erev.migration_batch cannot change from UPLOADED to PROMOTED",
        )
        session.execute(move(status="PROFILING", job_id=None, started_at=None))
        session.execute(move(status="PROFILED", profile={"contract_live_rows": 24}))
        assert _fails(session, move(source_sha256="00" * 32))[0] == INSUFFICIENT_PRIVILEGE
        # 04 rev 1.60 in place (D-98 candidate 128; Codex 0801 R1): cutover_date is granted and
        # SET ONCE — this row already carries one, so a change is the trigger's refusal, not a
        # privilege error; the frozen-column control above is preserved
        assert _fails(session, move(cutover_date=date(2023, 2, 28))) == (
            RAISE_EXCEPTION,
            "EREV-TRN-001: cutover_date of erev.migration_batch is already set",
        )
        session.execute(move(status="CANCELLED"))
        assert _fails(session, move(status="IMPORTING"))[0] == RAISE_EXCEPTION
        removed = delete(migration_batch).where(migration_batch.c.id == row["id"])
        assert _fails(session, removed)[0] in (INSUFFICIENT_PRIVILEGE, RAISE_EXCEPTION)


def test_t_mig_01_checks_and_source_uniqueness(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # ck_migration_batch__cutover; ux_migration_batch__source is partial: an active duplicate is
    # refused (BR-MIG-01; REQ-MIG-004), a cancelled one frees the digest.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        file_row = file_object_values(tenant_id, purpose=FilePurpose.LEGACY_DATABASE)
        session.execute(insert(file_object).values(**file_row))
        # 04 rev 1.60 in place (D-98 candidate 128; revision 0067): an OPENING_BALANCES batch is
        # created WITHOUT a cutover — the cutover is set once at /import; a second value is refused
        no_cutover = migration_batch_values(
            tenant_id, source_file_id=file_row["id"], cutover_date=None
        )
        session.execute(insert(migration_batch).values(**no_cutover))
        session.execute(
            update(migration_batch)
            .where(migration_batch.c.id == no_cutover["id"])
            .values(cutover_date=date(2023, 1, 31), row_version=2)
        )
        assert (
            "already set"
            in _fails(
                session,
                update(migration_batch)
                .where(migration_batch.c.id == no_cutover["id"])
                .values(cutover_date=date(2023, 2, 28), row_version=3),
            )[1]
        )
        replay_with_cutover = migration_batch_values(
            tenant_id, source_file_id=file_row["id"], mode="REPLAY"
        )
        assert (
            _fails(session, insert(migration_batch).values(**replay_with_cutover))[0]
            == CHECK_VIOLATION
        )
        first = migration_batch_values(tenant_id, source_file_id=file_row["id"])
        session.execute(insert(migration_batch).values(**first))
        again = migration_batch_values(
            tenant_id, source_file_id=file_row["id"], source_sha256=first["source_sha256"]
        )
        assert _fails(session, insert(migration_batch).values(**again))[0] == UNIQUE_VIOLATION
        session.execute(
            update(migration_batch)
            .where(migration_batch.c.id == first["id"])
            .values(status="CANCELLED")
        )
        session.execute(insert(migration_batch).values(**again))


def test_t_mig_02_and_03_checks_and_immutability(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # ck_migrated_legacy_row__label, ux_migrated_legacy_row__source, IM-A (DB-01) on both tables;
    # ck_migration_reconciliation_line__measure accepts ORIGINAL_ALLOCATION (04 rev 1.35) and
    # refuses an unknown measure.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        batch = _batch(session, tenant_id)
        legacy = migrated_legacy_row_values(tenant_id, migration_batch_id=batch["id"])
        session.execute(insert(migrated_legacy_row).values(**legacy))
        relabelled = migrated_legacy_row_values(
            tenant_id, migration_batch_id=batch["id"], source_rowid=2, label="attributed"
        )
        assert (
            _fails(session, insert(migrated_legacy_row).values(**relabelled))[0] == CHECK_VIOLATION
        )
        repeated = migrated_legacy_row_values(tenant_id, migration_batch_id=batch["id"])
        assert (
            _fails(session, insert(migrated_legacy_row).values(**repeated))[0] == UNIQUE_VIOLATION
        )
        touched = (
            update(migrated_legacy_row)
            .where(migrated_legacy_row.c.id == legacy["id"])
            .values(product_code="Other")
        )
        assert _fails(session, touched)[0] in (INSUFFICIENT_PRIVILEGE, RAISE_EXCEPTION)
        removed = delete(migrated_legacy_row).where(migrated_legacy_row.c.id == legacy["id"])
        assert _fails(session, removed)[0] in (INSUFFICIENT_PRIVILEGE, RAISE_EXCEPTION)

        line = migration_reconciliation_line_values(tenant_id, migration_batch_id=batch["id"])
        session.execute(insert(migration_reconciliation_line).values(**line))
        creation_time = migration_reconciliation_line_values(
            tenant_id,
            migration_batch_id=batch["id"],
            contract_external_id="Contract 3",
            obligation_key="POB #5",
            measure="ORIGINAL_ALLOCATION",
            source_value=Decimal("0"),
            erev_value=Decimal("1268.1139"),
            difference=Decimal("1268.1139"),
            is_within_tolerance=False,
            deviation_ref="DEV-052",
        )
        session.execute(insert(migration_reconciliation_line).values(**creation_time))
        unlinked = migration_reconciliation_line_values(
            tenant_id,
            migration_batch_id=batch["id"],
            obligation_key="POB #1",
            measure="REVENUE_CUM",
            source_value=Decimal("1"),
            erev_value=Decimal("2"),
            difference=Decimal("1"),
            is_within_tolerance=False,
        )  # ck_migration_reconciliation_line__exception (04 rev 1.36): no deviation, no item
        assert (
            _fails(session, insert(migration_reconciliation_line).values(**unlinked))[0]
            == CHECK_VIOLATION
        )
        unknown = migration_reconciliation_line_values(
            tenant_id, migration_batch_id=batch["id"], measure="SOMETHING_ELSE"
        )
        assert (
            _fails(session, insert(migration_reconciliation_line).values(**unknown))[0]
            == CHECK_VIOLATION
        )
        edited = (
            update(migration_reconciliation_line)
            .where(migration_reconciliation_line.c.id == line["id"])
            .values(is_within_tolerance=False)
        )
        assert _fails(session, edited)[0] in (INSUFFICIENT_PRIVILEGE, RAISE_EXCEPTION)


def test_unexplained_count_counts_a_linked_exception_line_without_a_deviation(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # Codex 0801 R2 (04 rev 1.60 in place; BR-MIG-02): the 0056 CHECK requires every
    # outside-tolerance line without a deviation reference to CARRY an exception item — such a line
    # is still UNEXPLAINED (an exception link is not an explanation): the API-R-48 list figure and
    # reconciliation.control_totals agree on 1
    from erev_api.db.tables import exception_item, migration_reconciliation_line
    from erev_api.domain.migration import queries

    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        row = _batch(session, tenant_id)
        item = exception_item_values(tenant_id)
        session.execute(insert(exception_item).values(**item))
        explained = migration_reconciliation_line_values(
            tenant_id, migration_batch_id=row["id"], is_within_tolerance=True, deviation_ref=None
        )
        deviated = migration_reconciliation_line_values(
            tenant_id,
            migration_batch_id=row["id"],
            obligation_key="POB #1",
            is_within_tolerance=False,
            deviation_ref="OQ-D7",
        )
        linked_only = migration_reconciliation_line_values(
            tenant_id,
            migration_batch_id=row["id"],
            obligation_key="POB #2",
            is_within_tolerance=False,
            deviation_ref=None,
            exception_item_id=item["id"],
        )
        for line in (explained, deviated, linked_only):
            session.execute(insert(migration_reconciliation_line).values(**line))
        assert queries.unexplained_counts(session, [row["id"]]) == {row["id"]: 1}
        # the CHECK itself refuses the line that would be neither explained nor linked
        bare = migration_reconciliation_line_values(
            tenant_id,
            migration_batch_id=row["id"],
            obligation_key="POB #3",
            is_within_tolerance=False,
            deviation_ref=None,
            exception_item_id=None,
        )
        assert _fails(session, insert(migration_reconciliation_line).values(**bare))[0] == (
            CHECK_VIOLATION
        )
