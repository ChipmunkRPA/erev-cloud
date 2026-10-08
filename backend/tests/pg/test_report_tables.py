"""Report table rules (04 T-RPT-01 to T-RPT-04; BUILD_SPEC RPS-1)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from importlib import import_module
from typing import Any

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db import migration_ops as ops
from erev_api.db import new_id
from erev_api.db.session import DbContext, identity_session, set_tenant_context, tenant_session
from erev_api.db.tables import (
    engine_release,
    evidence_pack,
    period_lock,
    report_definition,
    report_run,
)
from erev_api.domain.reports.catalogue import DEFINITIONS
from sqlalchemy import Executable, delete, exc, func, insert, select, text, update
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import (
    engine_release_values,
    evidence_pack_values,
    insert_close_parts,
    period_lock_values,
    report_run_values,
)

pytestmark = pytest.mark.pg

CHECK_VIOLATION = "23514"
INSUFFICIENT_PRIVILEGE = "42501"
RAISED = "P0001"
STARTED_AT = datetime(2026, 10, 1, 8, tzinfo=UTC)
FINISHED_AT = datetime(2026, 10, 1, 8, 5, tzinfo=UTC)


def _raised(session: Session, statement: Executable) -> Any:
    """The driver error of a statement that must fail; only its savepoint rolls back."""
    savepoint = session.begin_nested()
    with pytest.raises(exc.DBAPIError) as excinfo:
        session.execute(statement)
    savepoint.rollback()
    return excinfo.value.orig


def _failure(session: Session, statement: Executable) -> tuple[str | None, str]:
    """SQLSTATE and primary message of a statement that must fail."""
    orig = _raised(session, statement)
    diag = getattr(orig, "diag", None)
    return getattr(orig, "sqlstate", None), str(getattr(diag, "message_primary", "") or "")


def _violated(session: Session, statement: Executable) -> tuple[str | None, str | None]:
    """SQLSTATE and constraint name of a statement that must fail."""
    orig = _raised(session, statement)
    return getattr(orig, "sqlstate", None), getattr(
        getattr(orig, "diag", None), "constraint_name", None
    )


def _context(keyring: KeyRing) -> tuple[Any, DbContext]:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    return tenant_id, DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def test_report_definition_read_only(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # 04 T-RPT-01 and §14.2 (RPS-1; REQ-RPT-001): erev_app reads the global catalogue, with or
    # without a tenant context, and its INSERT, UPDATE and DELETE answer 42501. For erev_owner
    # without a data-fix ticket DB-01 refuses the UPDATE (EREV-IMM-001).
    tenant_id, context = _context(keyring)
    current = report_definition.c.is_current
    with tenant_session(context) as session:
        codes = list(session.scalars(select(report_definition.c.code).where(current)))
        assert len(codes) == 56
        assert {"revenue_waterfall", "disclosure_pack", "forecast_outputs"} <= set(codes)
        tenant_defined = {
            "code": "tenant_report",
            "version": 1,
            "name": "Tenant report",
            "kind": "STANDARD",
            "description": "A report the tenant defines.",
            "parameters_schema": {"type": "object", "additionalProperties": False},
            "output_formats": ["CSV"],
            "ipe_logic": {"version": 1},
            "tie_outs": [],
        }
        assert _failure(session, insert(report_definition).values(**tenant_defined))[0] == (
            INSUFFICIENT_PRIVILEGE
        )
        waterfall = report_definition.c.code == "revenue_waterfall"
        rename = update(report_definition).where(waterfall).values(name="Tampered")
        assert _failure(session, rename)[0] == INSUFFICIENT_PRIVILEGE
        assert _failure(session, delete(report_definition).where(waterfall))[0] == (
            INSUFFICIENT_PRIVILEGE
        )
        name = session.execute(select(report_definition.c.name).where(waterfall)).scalar_one()
        assert name == "Revenue waterfall"
    with identity_session(request_id="tests-rps-1-catalogue") as session:
        total = session.execute(select(func.count()).select_from(report_definition)).scalar_one()
        assert total == 56

    with committed_db.owner_engine.connect() as connection:
        connection.begin()
        try:
            savepoint = connection.begin_nested()
            with pytest.raises(exc.DBAPIError) as excinfo:
                connection.execute(
                    update(report_definition)
                    .where(report_definition.c.code == "revenue_waterfall")
                    .values(name="Tampered")
                )
            savepoint.rollback()
        finally:
            connection.rollback()
    diag = getattr(excinfo.value.orig, "diag", None)
    assert getattr(diag, "message_primary", None) == (
        "EREV-IMM-001: UPDATE on erev.report_definition is not permitted; the table is append-only"
    )


def test_report_definition_seed_equals_catalogue(test_database: TestDatabase) -> None:
    # DG-MIG-07 (RPS-1): the rows the revision seeds equal catalogue.DEFINITIONS column by column.
    with identity_session(request_id="tests-rps-1-seed") as session:
        rows = session.execute(select(report_definition)).mappings().all()
    stored = {str(row["code"]): dict(row) for row in rows}
    expected = {
        definition.code: {
            "code": definition.code,
            "version": definition.version,
            "name": definition.name,
            "kind": definition.kind,
            "description": definition.description,
            "parameters_schema": dict(definition.parameters_schema),
            "output_formats": list(definition.output_formats),
            "ipe_logic": dict(definition.ipe_logic),
            "tie_outs": list(definition.tie_outs),
            "is_current": definition.is_current,
        }
        for definition in DEFINITIONS
    }
    assert stored == expected


def test_report_run_frozen_after_finish(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # 04 T-RPT-02 and E-67 (RPS-1; REQ-RPT-002): QUEUED → RUNNING → SUCCEEDED; QUEUED → SUCCEEDED
    # and a second started_at raise EREV-TRN-001. Once SUCCEEDED, updating output_sha256 raises
    # EREV-TRN-001 and no status change is allowed; a FAILED run is frozen likewise. Identity
    # columns are not granted, and a run is never deleted (42501).
    tenant_id, context = _context(keyring)
    with tenant_session(context) as session:
        release = engine_release_values()
        session.execute(insert(engine_release).values(**release))
        run = report_run_values(tenant_id, engine_release_id=release["id"])
        session.execute(insert(report_run).values(**run))
        target = report_run.c.id == run["id"]

        def move(**values: Any) -> Executable:
            return update(report_run).where(target).values(**values)

        assert _failure(session, move(status="SUCCEEDED")) == (
            RAISED,
            "EREV-TRN-001: status of erev.report_run cannot change from QUEUED to SUCCEEDED",
        )
        session.execute(move(status="RUNNING", started_at=STARTED_AT))
        assert _failure(session, move(started_at=FINISHED_AT)) == (
            RAISED,
            "EREV-TRN-001: started_at of erev.report_run is already set",
        )
        session.execute(
            move(
                status="SUCCEEDED",
                finished_at=FINISHED_AT,
                output_sha256="a" * 64,
                row_count=3,
                control_totals={"client_count": 3},
                tie_out_results=[],
                ledger_heads={"ASC606": {"chain_seq": 0, "seal_sha256": None}},
            )
        )
        assert _failure(session, move(output_sha256="b" * 64)) == (
            RAISED,
            "EREV-TRN-001: columns output_sha256 of erev.report_run cannot change while status is "
            "SUCCEEDED",
        )
        assert _failure(session, move(status="RUNNING")) == (
            RAISED,
            "EREV-TRN-001: status of erev.report_run cannot change from SUCCEEDED to RUNNING",
        )
        assert _failure(session, move(report_code="rpo"))[0] == INSUFFICIENT_PRIVILEGE
        assert _failure(session, delete(report_run).where(target))[0] == INSUFFICIENT_PRIVILEGE
        stored = session.execute(
            select(report_run.c.status, report_run.c.output_sha256, report_run.c.row_count).where(
                target
            )
        ).one()
        assert tuple(stored) == ("SUCCEEDED", "a" * 64, 3)

        failed = report_run_values(tenant_id, engine_release_id=release["id"])
        session.execute(insert(report_run).values(**failed))
        failed_target = report_run.c.id == failed["id"]
        session.execute(
            update(report_run)
            .where(failed_target)
            .values(status="FAILED", finished_at=FINISHED_AT, problem={"title": "Builder failed"})
        )
        retitle = update(report_run).where(failed_target).values(problem={"title": "Other"})
        assert _failure(session, retitle) == (
            RAISED,
            "EREV-TRN-001: columns problem of erev.report_run cannot change while status is FAILED",
        )


def test_evidence_pack_checks(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # 04 T-RPT-04 checks (rev 1.2; RPS-1; REQ-RPT-014): a CLOSE pack without period_lock_id, a
    # CONTRACT_SAMPLE pack with empty contract_ids and a CHANGE pack with to_date < from_date each
    # answer 23514, as do a CHANGE pack without to_date and an ACCESS pack without as_of_date. A
    # pack of each kind with its required fields is stored.
    tenant_id, context = _context(keyring)
    with tenant_session(context) as session:
        parts = insert_close_parts(session, tenant_id)
        lock = period_lock_values(tenant_id, parts=parts)
        session.execute(insert(period_lock).values(**lock))
        close_scope = {
            "kind": "CLOSE",
            "entity_id": parts.entity_id,
            "book_code": "ASC606",
            "period_id": parts.period_id,
            "as_of_date": None,
        }
        september = {"from_date": date(2026, 9, 1), "to_date": date(2026, 9, 30)}
        refused = (
            ("ck_evidence_pack__close", evidence_pack_values(tenant_id, **close_scope)),
            (
                "ck_evidence_pack__sample",
                evidence_pack_values(tenant_id, kind="CONTRACT_SAMPLE", contract_ids=[]),
            ),
            (
                "ck_evidence_pack__date_range",
                evidence_pack_values(
                    tenant_id,
                    kind="CHANGE",
                    as_of_date=None,
                    from_date=date(2026, 9, 30),
                    to_date=date(2026, 9, 1),
                ),
            ),
            (
                "ck_evidence_pack__change",
                evidence_pack_values(
                    tenant_id, kind="CHANGE", as_of_date=None, from_date=date(2026, 9, 1)
                ),
            ),
            ("ck_evidence_pack__access", evidence_pack_values(tenant_id, as_of_date=None)),
        )
        for constraint, row in refused:
            outcome = _violated(session, insert(evidence_pack).values(**row))
            assert outcome == (CHECK_VIOLATION, constraint)

        stored = (
            evidence_pack_values(tenant_id, **close_scope, period_lock_id=lock["id"]),
            evidence_pack_values(tenant_id, kind="CONTRACT_SAMPLE", contract_ids=[new_id()]),
            evidence_pack_values(tenant_id, kind="CHANGE", as_of_date=None, **september),
            evidence_pack_values(tenant_id),
        )
        for row in stored:
            session.execute(insert(evidence_pack).values(**row))
        ids = [row["id"] for row in stored]
        count = select(func.count()).select_from(evidence_pack).where(evidence_pack.c.id.in_(ids))
        assert session.execute(count).scalar_one() == 4


def test_evidence_pack_frozen_after_success(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # 04 T-RPT-04 and E-67 (RPS-1): the manifest, its hash, the file and the report runs change
    # while a pack is not SUCCEEDED; afterwards only SC-M changes. The kind is not granted, and a
    # pack is never deleted (42501).
    tenant_id, context = _context(keyring)
    with tenant_session(context) as session:
        pack = evidence_pack_values(tenant_id)
        session.execute(insert(evidence_pack).values(**pack))
        target = evidence_pack.c.id == pack["id"]

        def move(**values: Any) -> Executable:
            return update(evidence_pack).where(target).values(**values)

        assert _failure(session, move(status="SUCCEEDED")) == (
            RAISED,
            "EREV-TRN-001: status of erev.evidence_pack cannot change from QUEUED to SUCCEEDED",
        )
        session.execute(move(status="RUNNING"))
        session.execute(move(manifest={"files": []}, manifest_sha256="d" * 64))
        manifest = {
            "files": [{"path": "access/users.csv", "sha256": "e" * 64, "bytes": 120}],
        }
        session.execute(move(status="SUCCEEDED", manifest=manifest, manifest_sha256="f" * 64))
        assert _failure(session, move(manifest_sha256="0" * 64)) == (
            RAISED,
            "EREV-TRN-001: columns manifest_sha256 of erev.evidence_pack cannot change while "
            "status is SUCCEEDED",
        )
        assert _failure(session, move(kind="CLOSE"))[0] == INSUFFICIENT_PRIVILEGE
        assert _failure(session, delete(evidence_pack).where(target))[0] == INSUFFICIENT_PRIVILEGE
        stored = session.execute(
            select(evidence_pack.c.status, evidence_pack.c.manifest_sha256).where(target)
        ).one()
        assert tuple(stored) == ("SUCCEEDED", "f" * 64)


def test_evidence_source_binding_is_immutable_and_cannot_be_discarded(
    committed_db: TestDatabase,
    keyring: KeyRing,
) -> None:
    tenant_id, context = _context(keyring)
    with tenant_session(context) as session:
        bad = evidence_pack_values(tenant_id, source_binding=["not an object"])
        assert _violated(session, insert(evidence_pack).values(**bad)) == (
            CHECK_VIOLATION,
            "ck_evidence_pack__source_binding",
        )
        pack = evidence_pack_values(tenant_id, source_binding={"format": "retained-test"})
        session.execute(insert(evidence_pack).values(**pack))
        target = evidence_pack.c.id == pack["id"]
        for value in (None, {"format": "replacement"}):
            assert (
                _failure(session, update(evidence_pack).where(target).values(source_binding=value))[
                    0
                ]
                == INSUFFICIENT_PRIVILEGE
            )
        session.commit()
    # Isolate DB-03 from grants/RLS: let the table owner see this synthetic row in a
    # transaction that rolls back the NO FORCE change as well as the attempted mutation.
    with committed_db.owner_engine.connect() as connection:
        connection.execute(text("ALTER TABLE erev.evidence_pack NO FORCE ROW LEVEL SECURITY"))
        set_tenant_context(connection, context)
        assert (
            connection.execute(select(evidence_pack.c.id).where(target)).scalar_one() == pack["id"]
        )
        with pytest.raises(exc.DBAPIError) as error:
            connection.execute(update(evidence_pack).where(target).values(source_binding=None))
        assert error.value.orig.sqlstate == RAISED
        connection.rollback()
    migration = import_module("erev_api.db.migrations.versions.0142_evidence_pack_source_binding")
    # No tenant context: downgrade must still detect data protected by tenant RLS.
    with committed_db.owner_engine.connect() as connection, ops.bound_to(connection):
        with pytest.raises(exc.DBAPIError) as error:
            migration.downgrade()
        assert error.value.orig.sqlstate == CHECK_VIOLATION
        connection.rollback()
    with tenant_session(context) as session:
        assert session.execute(
            select(evidence_pack.c.source_binding).where(target)
        ).scalar_one() == {"format": "retained-test"}
