"""Close table rules (04 T-CLS-01 to T-CLS-07, table 3.4-R; BUILD_SPEC CLO-2)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    close_checklist_item,
    close_checklist_template,
    close_run,
    exception_item,
    period_lock,
    reconciliation,
    reconciliation_item,
    role,
)
from sqlalchemy import Executable, delete, exc, func, insert, select, update
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import (
    close_checklist_item_values,
    close_checklist_template_values,
    close_run_steps,
    close_run_values,
    exception_item_values,
    insert_close_parts,
    insert_journal_rows,
    period_lock_values,
    reconciliation_item_values,
    reconciliation_values,
)

pytestmark = pytest.mark.pg

CHECK_VIOLATION = "23514"
FOREIGN_KEY_VIOLATION = "23503"
UNIQUE_VIOLATION = "23505"
INSUFFICIENT_PRIVILEGE = "42501"
STARTED_AT = datetime(2026, 10, 1, 8, tzinfo=UTC)


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


def test_close_run_transitions(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # 04 T-CLS-01 and PRD SM-14 (CLO-2): PENDING → RUNNING → SUCCEEDED, RUNNING → BLOCKED → RUNNING,
    # FAILED → RUNNING (resume) and RUNNING → CANCELLED succeed; PENDING → SUCCEEDED raises
    # EREV-TRN-001, and a second PENDING run of the same (entity, book, period) violates
    # ux_close_run__active. A SUCCEEDED run changes only the LOCK element of its steps (BS4-D-03).
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        parts = insert_close_parts(session, tenant_id)
        first = close_run_values(tenant_id, entity_id=parts.entity_id, period_id=parts.period_id)
        second = close_run_values(tenant_id, entity_id=parts.entity_id, period_id=parts.period_id)
        session.execute(insert(close_run).values(**first))

        def move(row: dict[str, Any], **values: Any) -> Executable:
            return update(close_run).where(close_run.c.id == row["id"]).values(**values)

        assert _violated(session, insert(close_run).values(**second)) == (
            UNIQUE_VIOLATION,
            "ux_close_run__active",
        )
        assert _failure(session, move(first, status="SUCCEEDED")) == (
            "P0001",
            "EREV-TRN-001: status of erev.close_run cannot change from PENDING to SUCCEEDED",
        )
        session.execute(
            move(first, status="RUNNING", started_at=STARTED_AT, current_step_code="CUTOFF")
        )
        session.execute(move(first, status="BLOCKED", current_step_code="RECOMPUTE_DIRTY"))
        session.execute(move(first, status="RUNNING"))
        session.execute(move(first, status="FAILED", finished_at=STARTED_AT))
        session.execute(move(first, status="RUNNING", finished_at=None))
        assert _failure(session, move(first, started_at=datetime(2026, 10, 2, tzinfo=UTC))) == (
            "P0001",
            "EREV-TRN-001: started_at of erev.close_run is already set",
        )
        # Steps 1 to 13 succeeded; the LOCK step waits for the lock job.
        finished = close_run_steps("SUCCEEDED", lock_status="PENDING")
        session.execute(
            move(
                first,
                status="SUCCEEDED",
                steps=finished,
                current_step_code="DATASET_FREEZE",
                finished_at=STARTED_AT,
            )
        )
        assert _failure(session, move(first, counts={"batches": 1})) == (
            "P0001",
            "EREV-TRN-001: columns counts of erev.close_run cannot change while status is "
            "SUCCEEDED",
        )
        element_only = (
            "P0001",
            "EREV-TRN-001: steps of erev.close_run change only in element LOCK while status is "
            "SUCCEEDED",
        )
        tampered = close_run_steps("SUCCEEDED", lock_status="PENDING")
        tampered[12]["problem"] = {"code": "TAMPERED"}
        assert _failure(session, move(first, steps=tampered)) == element_only
        assert _failure(session, move(first, steps=finished[:13])) == element_only
        assert _failure(session, move(first, status="RUNNING")) == (
            "P0001",
            "EREV-TRN-001: status of erev.close_run cannot change from SUCCEEDED to RUNNING",
        )
        session.execute(move(first, steps=close_run_steps("SUCCEEDED")))

        # Once the first run is no longer active, another run of the period starts; it is cancelled.
        session.execute(insert(close_run).values(**second))
        session.execute(move(second, status="RUNNING"))
        session.execute(move(second, status="CANCELLED"))
        assert _failure(session, move(second, status="RUNNING")) == (
            "P0001",
            "EREV-TRN-001: status of erev.close_run cannot change from CANCELLED to RUNNING",
        )
    with tenant_session(context, read_only=True) as session:
        stored = {
            row.id: (row.status, row.steps[-1]["status"], row.started_at)
            for row in session.execute(
                select(
                    close_run.c.id, close_run.c.status, close_run.c.steps, close_run.c.started_at
                )
            )
        }
    assert stored == {
        first["id"]: ("SUCCEEDED", "SUCCEEDED", STARTED_AT),
        second["id"]: ("CANCELLED", "PENDING", None),
    }


def test_close_run_records_what_it_read_once(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # 04 T-CLS-01 rev 1.291 (revision 0127; item CLO-RATE-AFTER-RUN-1): ``rates_read`` and
    # ``registry_read`` are NULL in a run until its first period-end step writes them, are written
    # once — with the step, while the run is RUNNING — and never again: a second write raises
    # EREV-TRN-001, and a SUCCEEDED run changes neither. A run that never wrote them keeps NULL.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    columns = ("rates_read", "registry_read")
    read = {"rates_read": "a" * 64, "registry_read": "b" * 64}
    with tenant_session(context) as session:
        parts = insert_close_parts(session, tenant_id)
        run = close_run_values(tenant_id, entity_id=parts.entity_id, period_id=parts.period_id)
        session.execute(insert(close_run).values(**run))

        def move(**values: Any) -> Executable:
            return update(close_run).where(close_run.c.id == run["id"]).values(**values)

        def stored() -> tuple[Any, ...]:
            return tuple(
                session.execute(
                    select(*(close_run.c[column] for column in columns)).where(
                        close_run.c.id == run["id"]
                    )
                ).one()
            )

        assert stored() == (None, None)
        session.execute(move(status="RUNNING", started_at=STARTED_AT, current_step_code="CUTOFF"))
        # the first period-end step ends: its counts and what it read, in one statement
        session.execute(move(current_step_code="FX_REMEASUREMENT", **read))
        assert stored() == ("a" * 64, "b" * 64)
        for column in columns:
            assert _failure(session, move(**{column: "c" * 64})) == (
                "P0001",
                f"EREV-TRN-001: {column} of erev.close_run is already set",
            )
            assert _failure(session, move(**{column: None})) == (
                "P0001",
                f"EREV-TRN-001: {column} of erev.close_run is already set",
            )
        session.execute(move(**read))  # the same values again change nothing
        finished = close_run_steps("SUCCEEDED", lock_status="PENDING")
        session.execute(
            move(
                status="SUCCEEDED",
                steps=finished,
                current_step_code="DATASET_FREEZE",
                finished_at=STARTED_AT,
            )
        )
        for column in columns:
            assert _failure(session, move(**{column: "c" * 64})) == (
                "P0001",
                f"EREV-TRN-001: columns {column} of erev.close_run cannot change while status is "
                "SUCCEEDED",
            )
        assert stored() == ("a" * 64, "b" * 64)
    # a run that ends without a period-end step keeps NULL in both
    with tenant_session(context) as session:
        parts = insert_close_parts(session, tenant_id)
        other = close_run_values(tenant_id, entity_id=parts.entity_id, period_id=parts.period_id)
        session.execute(insert(close_run).values(**other))
        session.execute(
            update(close_run)
            .where(close_run.c.id == other["id"])
            .values(status="RUNNING", started_at=STARTED_AT, current_step_code="CUTOFF")
        )
        session.execute(
            update(close_run)
            .where(close_run.c.id == other["id"])
            .values(status="CANCELLED", finished_at=STARTED_AT)
        )
        kept = session.execute(
            select(close_run.c.rates_read, close_run.c.registry_read).where(
                close_run.c.id == other["id"]
            )
        ).one()
        assert tuple(kept) == (None, None)


def test_system_template_rows_frozen(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # 04 T-CLS-02 class IM-M (CLO-2): a provisioned system template changes only in owner_role_id,
    # due_offset_days and SC-M and is never deleted; a tenant-defined task changes freely but never
    # becomes a system row.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    template = close_checklist_template
    with tenant_session(context) as session:
        gate_id = session.execute(
            select(template.c.id).where(template.c.code == "JE_BALANCED", template.c.is_system)
        ).scalar_one()
        controller_id = session.execute(
            select(role.c.id).where(role.c.code == "controller")
        ).scalar_one()
        gate = template.c.id == gate_id
        assert _failure(session, update(template).where(gate).values(code="JE-BALANCED")) == (
            "P0001",
            "EREV-TRN-001: columns code of system row JE_BALANCED of erev.close_checklist_template "
            "cannot change",
        )
        demoted = update(template).where(gate).values(is_system=False, name="Balanced journals")
        assert _failure(session, demoted) == (
            "P0001",
            "EREV-TRN-001: columns is_system, name of system row JE_BALANCED of "
            "erev.close_checklist_template cannot change",
        )
        session.execute(
            update(template)
            .where(gate)
            .values(owner_role_id=controller_id, due_offset_days=2, updated_by_kind="USER")
        )
        assert _failure(session, delete(template).where(gate))[0] == INSUFFICIENT_PRIVILEGE

        task = close_checklist_template_values(tenant_id, code="SALES-TAX-REVIEW")
        session.execute(insert(template).values(**task))
        own = template.c.id == task["id"]
        session.execute(
            update(template).where(own).values(code="SALES-TAX-REVIEW-2", name="Sales tax review")
        )
        assert _failure(session, update(template).where(own).values(is_system=True)) == (
            "P0001",
            "EREV-TRN-001: row SALES-TAX-REVIEW-2 of erev.close_checklist_template cannot become "
            "a system row",
        )
    with tenant_session(context, read_only=True) as session:
        stored = session.execute(
            select(
                template.c.code,
                template.c.owner_role_id,
                template.c.due_offset_days,
                template.c.is_system,
                template.c.row_version,
            ).where(gate)
        ).one()
        tasks = session.execute(
            select(func.count()).select_from(template).where(template.c.is_system.is_(False))
        ).scalar_one()
    assert tuple(stored) == ("JE_BALANCED", controller_id, 2, True, 2)
    assert tasks == 1


def test_check_constraints(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # 04 T-CLS-07 and table 3.4-R (CLO-2): an item kind outside the T-CLS-07 list, and a REOPEN lock
    # whose reason is outside the request-reopen subset or missing, fail with 23514. A direct GL
    # entry is high risk, an automatic template names a gate check code of T-CLS-02, and a WAIVED
    # item names its waiver request.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        parts = insert_close_parts(session, tenant_id)
        recon = reconciliation_values(
            tenant_id, entity_id=parts.entity_id, period_id=parts.period_id
        )
        session.execute(insert(reconciliation).values(**recon))
        rounding = reconciliation_item_values(
            tenant_id, reconciliation_id=recon["id"], item_kind="ROUNDING"
        )
        assert _violated(session, insert(reconciliation_item).values(**rounding)) == (
            CHECK_VIOLATION,
            "ck_reconciliation_item__item_kind",
        )
        restarted = period_lock_values(
            tenant_id, parts=parts, kind="REOPEN", reason_code="CLOSE_RESTARTED"
        )
        assert _violated(session, insert(period_lock).values(**restarted)) == (
            CHECK_VIOLATION,
            "ck_period_lock__reason_code",
        )
        unexplained = period_lock_values(tenant_id, parts=parts, kind="REOPEN")
        assert _violated(session, insert(period_lock).values(**unexplained)) == (
            CHECK_VIOLATION,
            "ck_period_lock__reason_code",
        )
        direct = reconciliation_item_values(
            tenant_id, reconciliation_id=recon["id"], item_kind="DIRECT_GL_ENTRY"
        )
        assert _violated(session, insert(reconciliation_item).values(**direct)) == (
            CHECK_VIOLATION,
            "ck_reconciliation_item__high_risk",
        )
        for gate_check_code in (None, "FX_RATES_LOADED"):
            automatic = close_checklist_template_values(
                tenant_id, gate_kind="AUTOMATIC", gate_check_code=gate_check_code
            )
            assert _violated(session, insert(close_checklist_template).values(**automatic)) == (
                CHECK_VIOLATION,
                "ck_close_checklist_template__gate_check_code",
            )
        task = close_checklist_template_values(tenant_id)
        session.execute(insert(close_checklist_template).values(**task))
        waived = close_checklist_item_values(
            tenant_id,
            template_id=task["id"],
            entity_id=parts.entity_id,
            period_id=parts.period_id,
            status="WAIVED",
        )
        assert _violated(session, insert(close_checklist_item).values(**waived)) == (
            CHECK_VIOLATION,
            "ck_close_checklist_item__waiver",
        )
        # Accepted: a reopen for late source data, a high-risk direct GL entry and a waived item
        # with its request; the reason of a LOCK is free.
        for lock in (
            period_lock_values(
                tenant_id, parts=parts, kind="REOPEN", reason_code="LATE_SOURCE_DATA"
            ),
            period_lock_values(tenant_id, parts=parts, reason_code="OTHER"),
        ):
            session.execute(insert(period_lock).values(**lock))
        session.execute(insert(reconciliation_item).values(**{**direct, "is_high_risk": True}))
        session.execute(
            insert(close_checklist_item).values(
                **{**waived, "waiver_approval_request_id": parts.approval_request_id}
            )
        )
    with tenant_session(context, read_only=True) as session:
        counts = tuple(
            session.execute(select(func.count()).select_from(table)).scalar_one()
            for table in (period_lock, reconciliation_item, close_checklist_item)
        )
    assert counts == (2, 1, 1)


def test_reconciliation_item_role_and_origin(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # 04 T-CLS-07 rev 1.253 (revision 0119; supervisor rulings R-68 (a), R-74): ``account_role`` is
    # one of the three contract balance roles; a NOT_STATED item names its role and carries no
    # subledger amount; ``origin_period_id`` is a period of the tenant; neither column is updatable.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        parts = insert_close_parts(session, tenant_id)
        recon = reconciliation_values(
            tenant_id, entity_id=parts.entity_id, period_id=parts.period_id
        )
        session.execute(insert(reconciliation).values(**recon))

        def item(**extra: Any) -> dict[str, Any]:
            return reconciliation_item_values(tenant_id, reconciliation_id=recon["id"], **extra)

        assert _violated(
            session, insert(reconciliation_item).values(**item(account_role="REVENUE"))
        ) == (CHECK_VIOLATION, "ck_reconciliation_item__account_role")
        for wrong in (
            # no role named
            item(item_kind="NOT_STATED", subledger_amount=None),
            # a subledger amount where the subledger states none
            item(item_kind="NOT_STATED", account_role="CONTRACT_LIABILITY"),
        ):
            assert _violated(session, insert(reconciliation_item).values(**wrong)) == (
                CHECK_VIOLATION,
                "ck_reconciliation_item__not_stated",
            )
        assert _violated(
            session, insert(reconciliation_item).values(**item(origin_period_id=new_id()))
        ) == (FOREIGN_KEY_VIOLATION, "fk_reconciliation_item__origin_period")
        # Accepted: the item of a role the subledger does not state, an item of a role's row, and
        # a late document with the period it is dated in.
        not_stated = item(
            item_kind="NOT_STATED",
            account_code=None,
            account_role="UNBILLED_RECEIVABLE",
            subledger_amount=None,
        )
        of_role = item(item_kind="OTHER", account_role="CONTRACT_ASSET")
        late = item(origin_period_id=parts.period_id)
        for accepted in (not_stated, of_role, late):
            session.execute(insert(reconciliation_item).values(**accepted))
        # IM-S: the columns of revision 0119 are written at INSERT only.
        for column, value in (("account_role", "CONTRACT_ASSET"), ("origin_period_id", None)):
            orig = _raised(
                session,
                update(reconciliation_item)
                .where(reconciliation_item.c.id == late["id"])
                .values(**{column: value}),
            )
            assert getattr(orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE, column
    with tenant_session(context, read_only=True) as session:
        stored = session.execute(
            select(
                reconciliation_item.c.item_kind,
                reconciliation_item.c.account_role,
                reconciliation_item.c.origin_period_id,
            ).order_by(reconciliation_item.c.id)
        ).all()
    assert [tuple(row) for row in stored] == [
        ("NOT_STATED", "UNBILLED_RECEIVABLE", None),
        ("OTHER", "CONTRACT_ASSET", None),
        ("AMOUNT_VARIANCE", None, parts.period_id),
    ]


def test_reconciliation_records_what_it_read(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # 04 T-CLS-06 rev 1.259 (revision 0121; item REC-GEN-LOCK-1): the chain position and the two
    # document counts are written by the INSERT of the generation, hold NULL in a row that names
    # none (a reconciliation generated before the revision), and are not updatable.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    columns = ("ledger_chain_seq", "source_documents_read", "subledger_documents_read")
    with tenant_session(context) as session:
        parts = insert_close_parts(session, tenant_id)
        earlier = reconciliation_values(
            tenant_id, entity_id=parts.entity_id, period_id=parts.period_id
        )
        read = reconciliation_values(
            tenant_id,
            entity_id=parts.entity_id,
            period_id=parts.period_id,
            ledger_chain_seq=7,
            source_documents_read=3,
            subledger_documents_read=12,
        )
        for row in (earlier, read):
            session.execute(insert(reconciliation).values(**row))
        # IM-S: none of the three is in the table's updatable columns.
        for column in columns:
            orig = _raised(
                session,
                update(reconciliation)
                .where(reconciliation.c.id == read["id"])
                .values(**{column: 99}),
            )
            assert getattr(orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE, column
    with tenant_session(context, read_only=True) as session:
        stored = {
            row.id: tuple(getattr(row, column) for column in columns)
            for row in session.execute(
                select(reconciliation.c.id, *(reconciliation.c[column] for column in columns))
            )
        }
    assert stored == {earlier["id"]: (None, None, None), read["id"]: (7, 3, 12)}


def test_exception_item_run_keys(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # T-IMP-05 (CTR-5, revision 0041) leaves the keys of exception_item.close_run_id and
    # journal_run_id to the revisions that create those tables (DG-MIG-03). Since the L4 merge put
    # chain B after chain A, 0046 adds fk_exception_item__journal_run and 0047
    # fk_exception_item__close_run: an unknown run id violates the key, stored runs pass.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        parts = insert_close_parts(session, tenant_id)
        run = close_run_values(tenant_id, entity_id=parts.entity_id, period_id=parts.period_id)
        session.execute(insert(close_run).values(**run))
        journal = insert_journal_rows(session, tenant_id)
        for column, constraint in (
            ("close_run_id", "fk_exception_item__close_run"),
            ("journal_run_id", "fk_exception_item__journal_run"),
        ):
            orphan = exception_item_values(tenant_id, **{column: new_id()})
            assert _violated(session, insert(exception_item).values(**orphan)) == (
                FOREIGN_KEY_VIOLATION,
                constraint,
            )
        linked = exception_item_values(
            tenant_id, close_run_id=run["id"], journal_run_id=journal.run["id"]
        )
        session.execute(insert(exception_item).values(**linked))
    with tenant_session(context, read_only=True) as session:
        stored = session.execute(
            select(exception_item.c.close_run_id, exception_item.c.journal_run_id)
        ).one()
    assert tuple(stored) == (run["id"], journal.run["id"])
