"""Database invariants DB-01 to DB-05, DB-09, DB-12 and DB-15 (04 §14.1; dev-guide DG-TST-21,
DG-TST-23; BUILD_SPEC FND-6, PLF-1, PLF-3, PLF-4, PLF-6)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

import pytest
import sqlalchemy as sa
from erev_api import periods
from erev_api.audit.chain import append_events
from erev_api.audit.writer import AuditActor, build_event
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext, system_principal
from erev_api.auth.sod import conflicts_for
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import migration_ops as ops
from erev_api.db import new_id
from erev_api.db.session import (
    DbContext,
    identity_session,
    platform_session,
    set_tenant_context,
    tenant_session,
)
from erev_api.db.tables import (
    access_review_campaign,
    access_review_item,
    account_mapping_rule,
    account_mapping_version,
    api_client,
    approval_decision,
    approval_delegation,
    audit_chain_head,
    audit_event,
    close_checklist_item,
    close_checklist_template,
    combination_group,
    combination_group_member,
    contract,
    contract_event,
    contract_version,
    customer,
    dimension_definition,
    event_submission,
    file_attachment,
    file_object,
    fiscal_calendar,
    fx_rate,
    fx_rate_set,
    fx_rate_set_version,
    gl_account,
    integration_connection,
    journal_batch,
    journal_line,
    journal_run,
    judgement_record,
    legal_entity,
    manual_adjustment,
    obligation,
    obligation_version,
    outbox_message,
    period,
    period_state,
    period_state_transition,
    pob_template,
    pob_template_version,
    policy_override,
    reconciliation,
    reconciliation_item,
    registry_version,
    role,
    role_assignment,
    rule,
    rule_set,
    rule_set_version,
    rule_test_case,
    security_event,
    signoff,
    sod_exception,
    sod_rule,
    ssp_book,
    ssp_book_version,
    ssp_entry,
    ssp_range,
    subledger_line,
    subledger_posting,
    subledger_posting_seal,
    support_grant,
    tenant_membership,
    tenant_snapshot,
    user_recovery_code,
)
from erev_api.db.tables import ledger_chain_head as ledger_chain_head_table
from erev_api.db.tables import product as product_table
from erev_api.db.tables import product_bundle_component as component_table
from erev_api.db.tables import tenant as tenant_table
from erev_api.db.transitions import apply
from erev_api.enums import (
    AccountRole,
    ApprovalRequestStatus,
    BookCode,
    ClearingPurpose,
    ConfigStatus,
    FilePurpose,
    MembershipStatus,
    PrincipalKind,
    RegistryScope,
    SourceSystem,
    TenantKind,
)
from erev_api.files.store import LocalFileStore
from erev_api.problems import Problem
from erev_api.uow import unit_of_work
from sqlalchemy import (
    Connection,
    CursorResult,
    Executable,
    delete,
    exc,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.orm import Session
from support.db import TestDatabase, fresh_head
from support.factories import tenant_factory, tenant_id_of
from support.rows import (
    JournalRows,
    RowContext,
    VersionRows,
    access_review_campaign_values,
    access_review_item_values,
    account_mapping_rule_values,
    account_mapping_version_values,
    api_client_values,
    approval_decision_values,
    approval_delegation_values,
    close_checklist_item_values,
    close_checklist_template_values,
    combination_group_member_values,
    combination_group_values,
    contract_event_values,
    customer_values,
    dimension_definition_values,
    event_submission_values,
    file_object_values,
    fiscal_calendar_values,
    fx_rate_set_values,
    fx_rate_set_version_values,
    fx_rate_values,
    gl_account_values,
    insert_active_membership,
    insert_app_user,
    insert_approval_request,
    insert_approval_step,
    insert_close_parts,
    insert_contract_rows,
    insert_file_object,
    insert_journal_parts,
    insert_journal_rows,
    insert_ledger_parts,
    insert_ledger_rows,
    insert_obligation_rows,
    insert_reopen_record,
    insert_role_assignment,
    insert_sandbox_tenant,
    insert_sod_exception,
    insert_sod_rule,
    insert_support_grant,
    insert_version_rows,
    integration_connection_values,
    journal_line_values,
    journal_run_values,
    judgement_record_values,
    ledger_seal_values,
    legal_entity_values,
    manual_adjustment_values,
    obligation_version_values,
    period_state_transition_values,
    period_state_values,
    period_values,
    pob_template_values,
    pob_template_version_values,
    policy_override_values,
    product_bundle_component_values,
    product_values,
    reconciliation_item_values,
    reconciliation_values,
    registry_version_values,
    rule_set_values,
    rule_set_version_values,
    rule_test_case_values,
    rule_values,
    signoff_values,
    sod_exception_values,
    sod_rule_values,
    ssp_book_values,
    ssp_book_version_values,
    ssp_entry_values,
    ssp_range_values,
    subledger_line_values,
    subledger_posting_values,
    support_grant_values,
)

pytestmark = pytest.mark.pg

PROBE_ID = UUID("0191e0a0-0000-7000-8000-0000000000d1")
CREATE_PARTITION_PROBE = (
    "CREATE TABLE erev.partition_probe (id uuid, occurred_at timestamptz) "
    "PARTITION BY RANGE (occurred_at)"
)
PROBE_PARTITIONS = ("erev.partition_probe_p202609", "erev.partition_probe_pdefault")


def _error(excinfo: pytest.ExceptionInfo[exc.DBAPIError]) -> tuple[str | None, str]:
    orig = excinfo.value.orig
    diag = getattr(orig, "diag", None)
    return getattr(orig, "sqlstate", None), str(getattr(diag, "message_primary", "") or "")


@pytest.fixture
def append_only_probe(test_database: TestDatabase) -> Iterator[str]:
    """An IM-A probe committed as erev_owner, so an erev_app connection can see it.

    erev_owner cannot SET ROLE erev_app, so the probe cannot live in one owner transaction; it is
    dropped at teardown, which keeps the migration round trip free of leftovers (SPEC-Q-20).
    """
    owner = test_database.owner_engine
    with owner.begin() as connection, ops.bound_to(connection):
        ops.create_global_table(
            "probe_append_only",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("note", sa.Text(), nullable=False),
            primary_key=["id"],
        )
        ops.apply_class("probe_append_only", "IM-A")
        connection.execute(
            text("INSERT INTO erev.probe_append_only (id, note) VALUES (:id, 'before')"),
            {"id": PROBE_ID},
        )
    try:
        yield "erev.probe_append_only"
    finally:
        with owner.begin() as connection, ops.bound_to(connection):
            ops.drop_global_table("probe_append_only")


def _expect_failure(connection: Connection, statement: str) -> tuple[str | None, str]:
    savepoint = connection.begin_nested()
    with pytest.raises(exc.DBAPIError) as excinfo:
        connection.exec_driver_sql(statement)
    savepoint.rollback()
    return _error(excinfo)


def test_db_09_audit_chain_continuity(committed_db: TestDatabase, keyring: KeyRing) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    actor = AuditActor(
        kind=PrincipalKind.SYSTEM,
        id=None,
        roles=(),
        auth_method="system",
        mfa_verified=False,
        on_behalf_of_id=None,
        api_client_id=None,
        support_grant_id=None,
        source_ip=None,
        request_id="tests-db-09",
    )
    event = build_event(
        tenant_id=tenant_id,
        actor=actor,
        occurred_at=datetime(2026, 9, 12, 12, tzinfo=UTC),
        action="tenant.update",
        object_type="tenant",
        object_id=tenant_id,
    )
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        # Provisioning's events hold the first positions (04 §14.3).
        before = session.execute(select(audit_chain_head)).mappings().one()
        # Passing: the next position advances the head.
        assert append_events(session, tenant_id=tenant_id, keyring=keyring, events=[event]) == 1
        head = session.execute(select(audit_chain_head)).mappings().one()
        assert head["last_chain_seq"] == before["last_chain_seq"] + 1
        # Violating: the new position again, after the head moved on.
        repeat = {
            **event,
            "id": new_id(),
            "chain_seq": head["last_chain_seq"],
            "prev_hmac": before["last_hmac"],
            "hmac": "2" * 64,
            "hmac_key_id": f"audit-hmac:{tenant_id}:1",
        }
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as excinfo:
            session.execute(insert(audit_event).values(**repeat))
        savepoint.rollback()
    sqlstate, message = _error(excinfo)
    assert sqlstate == "P0001"
    assert message.startswith("EREV-AUD-001")


def test_db_09_chain_head_advances_only_through_append(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        before = session.execute(select(audit_chain_head)).mappings().one()
        # D-80: erev_app holds UPDATE on the head, but only tg_audit_event__chain may advance it.
        for statement in (
            "UPDATE erev.audit_chain_head SET last_chain_seq = last_chain_seq - 1",
            "UPDATE erev.audit_chain_head "
            "SET last_chain_seq = last_chain_seq, last_hmac = last_hmac",
        ):
            savepoint = session.begin_nested()
            with pytest.raises(exc.DBAPIError) as excinfo:
                session.execute(text(statement))
            savepoint.rollback()
            sqlstate, message = _error(excinfo)
            assert sqlstate == "P0001", statement
            assert message.startswith("EREV-AUD-001"), message

    ctx = RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-db-09-head",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    files = LocalFileStore(app_settings.file_root)
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        uow.audit(action="tenant.update", object_type="tenant", object_id=tenant_id)
        uow.commit()
    with tenant_session(context) as session:
        after = session.execute(select(audit_chain_head)).mappings().one()
    assert after["last_chain_seq"] == before["last_chain_seq"] + 1


def test_db_01_forbid_mutation(test_database: TestDatabase, append_only_probe: str) -> None:
    # The probe name is a fixture identifier; identifiers cannot be bound parameters.
    update = f"UPDATE {append_only_probe} SET note = 'after'"  # noqa: S608
    delete = f"DELETE FROM {append_only_probe}"  # noqa: S608
    truncate = f"TRUNCATE {append_only_probe}"
    select = f"SELECT note FROM {append_only_probe}"  # noqa: S608
    with identity_session(request_id="tests-db-01") as session:
        connection = session.connection()
        assert _expect_failure(connection, update)[0] == "42501"
        assert _expect_failure(connection, delete)[0] == "42501"
        assert _expect_failure(connection, truncate)[0] == "42501"

    with test_database.owner_engine.connect() as connection:
        connection.begin()
        try:
            for statement in (update, delete, truncate):
                sqlstate, message = _expect_failure(connection, statement)
                assert sqlstate == "P0001"
                assert message.startswith("EREV-IMM-001")
            connection.execute(text("SELECT set_config('app.data_fix_ticket', 'DF-0001', true)"))
            assert connection.exec_driver_sql(update).rowcount == 1
            note = connection.exec_driver_sql(select).scalar_one()
            assert note == "after"
        finally:
            connection.rollback()


@pytest.fixture(params=["A", "B"])
def partition_probe(request: pytest.FixtureRequest, test_database: TestDatabase) -> Iterator[str]:
    """A committed partitioned IM-A probe, built with the class first (A) or partitions first (B).

    Dropped at teardown, as the SPEC-Q-20 probe is.
    """

    def classify() -> None:
        ops.apply_class("partition_probe", "IM-A")

    def partition() -> None:
        ops.create_monthly_partitions(
            "partition_probe", first="2026-09", last="2026-10", partition_column="occurred_at"
        )

    steps = (classify, partition) if request.param == "A" else (partition, classify)
    owner = test_database.owner_engine
    with owner.begin() as connection, ops.bound_to(connection):
        connection.exec_driver_sql(CREATE_PARTITION_PROBE)
        for step in steps:
            step()
    try:
        yield "erev.partition_probe"
    finally:
        with owner.begin() as connection, ops.bound_to(connection):
            ops.drop_global_table("partition_probe")


def test_db_01_forbid_truncate_on_partitions(
    test_database: TestDatabase, partition_probe: str
) -> None:
    with test_database.owner_engine.connect() as connection:
        connection.begin()
        try:
            for table in (*PROBE_PARTITIONS, partition_probe):
                sqlstate, message = _expect_failure(connection, f"TRUNCATE {table}")
                assert sqlstate == "P0001", table
                assert message.startswith("EREV-IMM-001"), table
            connection.execute(text("SELECT set_config('app.data_fix_ticket', 'DF-0002', true)"))
            for partition in PROBE_PARTITIONS:
                connection.exec_driver_sql(f"TRUNCATE {partition}")
        finally:
            connection.rollback()


def test_db_02_touch_increments_row_version(test_database: TestDatabase) -> None:
    with test_database.owner_engine.connect() as connection, ops.bound_to(connection):
        connection.begin()
        try:
            ops.create_global_table(
                "probe_touch",
                sa.Column("id", sa.Uuid(), nullable=False),
                sa.Column("note", sa.Text(), nullable=False),
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.text("now()"),
                ),
                sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
                sa.Column("row_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
                primary_key=["id"],
            )
            ops.apply_class("probe_touch", "IM-M")
            connection.execute(
                text(
                    "INSERT INTO erev.probe_touch (id, note, updated_at) "
                    "VALUES (:id, 'before', '2026-01-01T00:00:00Z')"
                ),
                {"id": PROBE_ID},
            )
            connection.exec_driver_sql("UPDATE erev.probe_touch SET note = 'after'")
            row = connection.execute(
                text(
                    "SELECT row_version, updated_at > '2026-01-01T00:00:00Z', updated_at = now() "
                    "FROM erev.probe_touch"
                )
            ).one()
            assert tuple(row) == (2, True, True)

            sqlstate, message = _expect_failure(
                connection,
                "UPDATE erev.probe_touch SET id = '0191e0a0-0000-7000-8000-0000000000d2'",
            )
            assert sqlstate == "P0001"
            assert message.startswith("EREV-ROW-001")
            sqlstate, message = _expect_failure(
                connection, "UPDATE erev.probe_touch SET created_at = now() - interval '1 day'"
            )
            assert message.startswith("EREV-ROW-001")
        finally:
            connection.rollback()


def test_db_05_tenant_kind_immutable(committed_db: TestDatabase, keyring: KeyRing) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    own = tenant_table.c.id == tenant_id
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        renamed = session.execute(
            update(tenant_table).where(own).values(display_name="Renamed", updated_by_kind="SYSTEM")
        )
        assert cast(CursorResult[Any], renamed).rowcount == 1
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as excinfo:
            session.execute(update(tenant_table).where(own).values(kind="sandbox"))
        savepoint.rollback()
    sqlstate, message = _error(excinfo)
    assert sqlstate == "P0001"
    assert message.startswith("EREV-REF-001")


def test_db_05_period_gap_rejected(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DB-05 (RFD-1): the periods of a calendar are contiguous without overlap (EREV-REF-001).
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    calendar = fiscal_calendar_values(tenant_id)
    january = period_values(tenant_id, calendar_id=calendar["id"])

    def february(start: date) -> Executable:
        row = period_values(
            tenant_id,
            calendar_id=calendar["id"],
            period_no=2,
            start_date=start,
            end_date=date(2026, 2, 28),
        )
        return insert(period).values(**row)

    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        session.execute(insert(fiscal_calendar).values(**calendar))
        session.execute(insert(period).values(**january))

        # A February starting on 2 February leaves a one-day gap; one starting on 31 January
        # overlaps January.
        for start, reason in ((date(2026, 2, 2), "leaves a gap"), (date(2026, 1, 31), "overlaps")):
            sqlstate, message = _fails(session, february(start))
            assert sqlstate == "P0001"
            assert message.startswith("EREV-REF-001"), message
            assert reason in message, message

        # The contiguous February is accepted.
        session.execute(february(date(2026, 2, 1)))
        # Shortening January would open a gap before February.
        shorten = (
            update(period).where(period.c.id == january["id"]).values(end_date=date(2026, 1, 30))
        )
        sqlstate, message = _fails(session, shorten)
        assert (sqlstate, message.startswith("EREV-REF-001")) == ("P0001", True), message

        # Another calendar's periods are independent of this one.
        other = fiscal_calendar_values(tenant_id)
        session.execute(insert(fiscal_calendar).values(**other))
        july = period_values(
            tenant_id,
            calendar_id=other["id"],
            fiscal_year=2027,
            start_date=date(2026, 7, 1),
            end_date=date(2026, 7, 31),
        )
        session.execute(insert(period).values(**july))


def _future_period_state(
    session: Session, tenant_id: UUID
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """A January calendar holding FY2026-P01 only, an entity of it and the future ASC606 state of
    the period, inserted as erev_app."""
    calendar = fiscal_calendar_values(tenant_id)
    session.execute(insert(fiscal_calendar).values(**calendar))
    january = period_values(tenant_id, calendar_id=calendar["id"])
    session.execute(insert(period).values(**january))
    entity = legal_entity_values(tenant_id, calendar_id=calendar["id"])
    session.execute(insert(legal_entity).values(**entity))
    state = period_state_values(tenant_id, entity_id=entity["id"], period_id=january["id"])
    session.execute(insert(period_state).values(**state))
    return calendar, january, entity, state


def _transition(
    tenant_id: UUID,
    state: dict[str, Any],
    *,
    from_state: str | None,
    to_state: str,
    **values: Any,
) -> Executable:
    row = period_state_transition_values(
        tenant_id,
        period_state_id=state["id"],
        entity_id=state["entity_id"],
        period_id=state["period_id"],
        from_state=from_state,
        to_state=to_state,
        **values,
    )
    return insert(period_state_transition).values(**row)


def _set_state(state: dict[str, Any], value: str) -> Executable:
    return (
        update(period_state)
        .where(period_state.c.id == state["id"])
        .values(state=value, updated_by_kind="SYSTEM")
    )


def test_db_07_period_state_update_without_transition_rejected(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-07 (RFD-2): tg_period_state__update needs a transition row of this transaction whose pair
    # equals the change (EREV-PER-001).
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        _, _, _, state = _future_period_state(session, tenant_id)
        sqlstate, message = _fails(session, _set_state(state, "open"))
        assert (sqlstate, message.startswith("EREV-PER-001")) == ("P0001", True), message
        assert "moved from future to open without a transition" in message
        # A transition committed in an earlier transaction does not count.
        session.execute(_transition(tenant_id, state, from_state="future", to_state="open"))

    with tenant_session(context) as session:
        sqlstate, message = _fails(session, _set_state(state, "open"))
        assert (sqlstate, message.startswith("EREV-PER-001")) == ("P0001", True), message
        # A transition of another pair in this transaction does not count either.
        session.execute(_transition(tenant_id, state, from_state=None, to_state="future"))
        sqlstate, message = _fails(session, _set_state(state, "open"))
        assert (sqlstate, message.startswith("EREV-PER-001")) == ("P0001", True), message
        # With future → open in the same transaction the change is accepted.
        session.execute(_transition(tenant_id, state, from_state="future", to_state="open"))
        session.execute(_set_state(state, "open"))
        stored = select(period_state.c.state).where(period_state.c.id == state["id"])
        assert session.execute(stored).scalar_one() == "open"
        # The entity, book and period of a state never change.
        moved = (
            update(period_state)
            .where(period_state.c.id == state["id"])
            .values(book_code="IFRS15", updated_by_kind="SYSTEM")
        )
        sqlstate, message = _fails(session, moved)
        assert (sqlstate, message.startswith("EREV-PER-001")) == ("P0001", True), message


def test_db_07_invalid_pair_rejected(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DB-07 with T-REF-07: future → closed is no allowed pair, as a transition row or as a change.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        _, _, _, state = _future_period_state(session, tenant_id)
        approved = {"approval_request_id": PROBE_ID, "period_lock_id": PROBE_ID}
        closed = _transition(tenant_id, state, from_state="future", to_state="closed", **approved)
        assert _fails(session, closed) == (
            "P0001",
            "EREV-PER-001: erev.period_state_transition allows no transition from future to closed",
        )
        sqlstate, message = _fails(session, _set_state(state, "closed"))
        assert (sqlstate, message.startswith("EREV-PER-001")) == ("P0001", True), message
        assert "cannot move from future to closed" in message
        reopened = _transition(tenant_id, state, from_state="open", to_state="reopened", **approved)
        sqlstate, message = _fails(session, reopened)
        assert message.startswith("EREV-PER-001"), message
        # The T-REF-07 column checks: closing → open names a reason of its subset, and → closed
        # needs the approval and the lock.
        restart = _transition(
            tenant_id, state, from_state="closing", to_state="open", reason_code="DUPLICATE"
        )
        assert _fails(session, restart)[0] == "23514"
        # … and a missing reason is refused for both pairs that ask one (04 T-REF-07 rev 1.184,
        # revision 0113): a NULL reason compared with the subset is unknown, which a CHECK lets
        # pass — the two terms of 0029 did, although the column note says "Required"
        unreasoned = _transition(tenant_id, state, from_state="closing", to_state="open")
        assert _fails(session, unreasoned)[0] == "23514"
        bare_reopen = _transition(
            tenant_id, state, from_state="closed", to_state="reopened", **approved
        )
        assert _fails(session, bare_reopen)[0] == "23514"
        unapproved = _transition(tenant_id, state, from_state="closing", to_state="closed")
        assert _fails(session, unapproved)[0] == "23514"
        # Allowed pairs pass: creation, and closing → open with CLOSE_RESTARTED.
        session.execute(_transition(tenant_id, state, from_state=None, to_state="future"))
        session.execute(
            _transition(
                tenant_id,
                state,
                from_state="closing",
                to_state="open",
                reason_code="CLOSE_RESTARTED",
            )
        )


def test_db_07_end_of_a_soft_close_returns_to_reopened(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-07 with T-REF-07 rev 1.170 (revision 0107; CLO-CANCEL-CLOSE-REOPENED-1): closing →
    # reopened is an allowed pair — the end of a soft close of a period that has been locked
    # before. Its row carries a reason of the cancel subset and names neither an approval request
    # nor a lock record; closed → reopened keeps requiring both.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        _, _, _, state = _future_period_state(session, tenant_id)
        approved = {"approval_request_id": PROBE_ID, "period_lock_id": PROBE_ID}

        def back(**values: Any) -> Executable:
            return _transition(
                tenant_id, state, from_state="closing", to_state="reopened", **values
            )

        # no reason, or a reason of the reopen subset: refused by the reason check
        assert _fails(session, back())[0] == "23514"
        assert _fails(session, back(reason_code="ERROR_CORRECTION"))[0] == "23514"
        # an approval request or a lock record on the row: refused, each by its own check
        named = back(reason_code="CLOSE_RESTARTED", **approved)
        assert _fails(session, named)[0] == "23514"
        with_request = back(reason_code="CLOSE_RESTARTED", approval_request_id=PROBE_ID)
        assert _fails(session, with_request)[0] == "23514"
        with_record = back(reason_code="CLOSE_RESTARTED", period_lock_id=PROBE_ID)
        assert _fails(session, with_record)[0] == "23514"
        # the pair itself passes, for each reason of the cancel subset
        for reason in ("CLOSE_RESTARTED", "DATA_CORRECTION_PENDING", "OTHER"):
            session.execute(back(reason_code=reason))
        # closed → reopened is unchanged: it asks a reopen reason and both references (its
        # accepted row needs a real lock record: tests/domain/close/test_reopen.py)
        reopen = {"from_state": "closed", "to_state": "reopened"}
        bare = _transition(tenant_id, state, reason_code="ERROR_CORRECTION", **reopen)
        assert _fails(session, bare)[0] == "23514"
        cancel_reason = _transition(
            tenant_id, state, reason_code="CLOSE_RESTARTED", **reopen, **approved
        )
        assert _fails(session, cancel_reason)[0] == "23514"
        # and the state itself moves closing → reopened only with its transition row
        # (tg_period_state__update): future → open → closing first.
        for source, target in (("future", "open"), ("open", "closing")):
            session.execute(_transition(tenant_id, state, from_state=source, to_state=target))
            session.execute(_set_state(state, target))
        session.execute(back(reason_code="OTHER"))
        session.execute(_set_state(state, "reopened"))
        stored = select(period_state.c.state).where(period_state.c.id == state["id"])
        assert session.execute(stored).scalar_one() == "reopened"
        # a pair outside T-REF-07 stays refused: open → reopened
        stray = _transition(tenant_id, state, from_state="open", to_state="reopened", **approved)
        assert _fails(session, stray)[1].startswith("EREV-PER-001")


def test_db_05_period_frozen_when_state_not_future(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-05 (RFD-2): a period, and the pattern fields of its calendar, freeze once a period state
    # other than future references the period (EREV-REF-001).
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        calendar, january, _, state = _future_period_state(session, tenant_id)

        def shorten(end: date) -> Executable:
            return (
                update(period)
                .where(period.c.id == january["id"])
                .values(end_date=end, updated_by_kind="SYSTEM")
            )

        repattern = (
            update(fiscal_calendar)
            .where(fiscal_calendar.c.id == calendar["id"])
            .values(fiscal_year_start_month=4, updated_by_kind="SYSTEM")
        )
        # While the state is future the period and the pattern may change (one period, no gap).
        session.execute(shorten(date(2026, 1, 30)))
        session.execute(
            update(fiscal_calendar)
            .where(fiscal_calendar.c.id == calendar["id"])
            .values(week_end_day=None, updated_by_kind="SYSTEM")
        )
        session.execute(_transition(tenant_id, state, from_state="future", to_state="open"))
        session.execute(_set_state(state, "open"))

        assert _fails(session, shorten(date(2026, 1, 31))) == (
            "P0001",
            "EREV-REF-001: period FY2026-P01 of erev.period is frozen: a period state beyond "
            "future references it",
        )
        assert _fails(session, repattern) == (
            "P0001",
            f"EREV-REF-001: the pattern of calendar {calendar['code']} of erev.fiscal_calendar is "
            "frozen: a period state beyond future references its periods",
        )
        # A calendar rename is not a pattern change.
        session.execute(
            update(fiscal_calendar)
            .where(fiscal_calendar.c.id == calendar["id"])
            .values(name="Renamed calendar", updated_by_kind="SYSTEM")
        )


def test_db_12_role_assignment_unknown_entity_rejected(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-12 (RFD-2): role_assignment.entity_ids and api_client.entity_ids name legal entities of
    # the tenant (EREV-REF-002).
    result = tenant_factory(keyring=keyring)
    tenant_id = tenant_id_of(result)
    other_tenant = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(
        DbContext(tenant_id=other_tenant, user_id=None, entity_scope="*")
    ) as session:
        _, _, foreign, _ = _future_period_state(session, other_tenant)
    assign = {
        "tenant_id": tenant_id,
        "membership_id": result.admin_membership_id,
        "role_code": "viewer",
    }
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        _, _, entity, _ = _future_period_state(session, tenant_id)
        for entity_ids in ((entity["id"], PROBE_ID), (foreign["id"],)):
            savepoint = session.begin_nested()
            with pytest.raises(exc.DBAPIError) as excinfo:
                insert_role_assignment(session, entity_ids=entity_ids, **assign)
            savepoint.rollback()
            unknown = ", ".join(str(value) for value in entity_ids if value != entity["id"])
            assert _error(excinfo) == (
                "P0001",
                "EREV-REF-002: entity_ids of erev.role_assignment name no existing legal entity: "
                + unknown,
            )
        insert_role_assignment(session, entity_ids=(entity["id"],), **assign)
        scoped = select(role_assignment.c.entity_ids).where(
            role_assignment.c.is_all_entities.is_(False)
        )
        assert [list(ids) for ids in session.scalars(scoped)] == [[entity["id"]]]

        client = api_client_values(tenant_id, is_all_entities=False, entity_ids=[entity["id"]])
        session.execute(insert(api_client).values(**client))
        widened = (
            update(api_client)
            .where(api_client.c.id == client["id"])
            .values(entity_ids=[entity["id"], PROBE_ID])
        )
        assert _fails(session, widened) == (
            "P0001",
            "EREV-REF-002: entity_ids of erev.api_client name no existing legal entity: "
            + str(PROBE_ID),
        )


def test_db_12_sixth_custom_dimension_rejected(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-12 (RFD-6): at most five non-built-in dimension_definition rows per tenant (EREV-REF-002).
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        # Provisioning wrote the five built-in rows; they do not count.
        builtin = (
            select(func.count())
            .select_from(dimension_definition)
            .where(dimension_definition.c.is_builtin)
        )
        assert session.execute(builtin).scalar_one() == 5
        customs = [dimension_definition_values(tenant_id, position=6 + n) for n in range(5)]
        for row in customs:
            session.execute(insert(dimension_definition).values(**row))

        sixth = dimension_definition_values(tenant_id, position=11)
        sqlstate, message = _fails(session, insert(dimension_definition).values(**sixth))
        assert (sqlstate, message.startswith("EREV-REF-002")) == ("P0001", True), message
        # Turning a built-in row into a custom one would make a sixth as well.
        demote = (
            update(dimension_definition)
            .where(dimension_definition.c.code == "department")
            .values(is_builtin=False, updated_by_kind="SYSTEM")
        )
        sqlstate, message = _fails(session, demote)
        assert (sqlstate, message.startswith("EREV-REF-002")) == ("P0001", True), message

        # A further built-in row, and an edit of a custom row, are accepted.
        extra = dimension_definition_values(tenant_id, is_builtin=True, position=12)
        session.execute(insert(dimension_definition).values(**extra))
        session.execute(
            update(dimension_definition)
            .where(dimension_definition.c.id == customs[0]["id"])
            .values(name="Renamed", updated_by_kind="SYSTEM")
        )

    # Another tenant's custom dimensions are counted separately.
    other = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=other, user_id=None, entity_scope="*")) as session:
        session.execute(insert(dimension_definition).values(**dimension_definition_values(other)))


def test_db_15_tenant_insert_requires_provisioning_scope(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    tenant_id = new_id()
    row = {
        "id": tenant_id,
        "code": f"db15-{tenant_id.hex[-12:]}",
        "kind": "production",
        "display_name": "DB-15 probe",
        "reporting_currency": "USD",
        "audit_hmac_key_id": keyring.new_tenant_audit_key_id(tenant_id),
        "created_by_kind": "OPERATOR",
        "updated_by_kind": "OPERATOR",
    }
    ctx = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx) as session:
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as excinfo:
            session.execute(insert(tenant_table).values(**row))
        savepoint.rollback()
    assert _error(excinfo)[0] == "42501"

    with platform_session("provisioning", actor_user_id=None, request_id="r-provision") as session:
        session.execute(insert(tenant_table).values(**row))
        txid = int(session.execute(text("SELECT txid_current()")).scalar_one())
    # xmin holds the 32-bit transaction id; txid_current() adds the epoch above it.
    same_transaction = text("xmin::text::bigint = :xid").bindparams(xid=txid % 2**32)
    with identity_session(request_id="tests-db-15") as session:
        events = session.execute(
            select(security_event.c.kind, security_event.c.detail).where(
                security_event.c.request_id == "r-provision", same_transaction
            )
        ).all()
    assert [tuple(event) for event in events] == [
        ("PLATFORM_SCOPE_USED", {"scope": "provisioning"})
    ]
    with tenant_session(ctx) as session:
        kind = session.execute(select(tenant_table.c.kind).where(tenant_table.c.id == tenant_id))
        assert kind.scalar_one() == "production"


REVOKED_AT = datetime(2026, 9, 12, 12, tzinfo=UTC)
USED_AT = datetime(2026, 9, 12, 12, 5, tzinfo=UTC)


def test_db_03_role_assignment_columns(committed_db: TestDatabase, keyring: KeyRing) -> None:
    result = tenant_factory(keyring=keyring)
    tenant_id = tenant_id_of(result)
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        assignment_id = insert_role_assignment(
            session,
            tenant_id=tenant_id,
            membership_id=result.admin_membership_id,
            role_code="viewer",
        )
        auditor_id = session.execute(select(role.c.id).where(role.c.code == "auditor")).scalar_one()
        # Passing: an allow-listed column changes.
        row = apply(
            session,
            "role_assignment",
            assignment_id,
            to_status=None,
            set_values={"revoked_at": REVOKED_AT, "revoked_by_kind": "SYSTEM"},
        )
        assert (row["revoked_at"], row["revoked_by_kind"]) == (REVOKED_AT, "SYSTEM")
        # erev_app holds UPDATE on the allow-listed columns only (04 §1.5, §14.2), so the grant
        # refuses role_id before the trigger runs (SPEC-Q-140).
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as refused:
            session.execute(
                update(role_assignment)
                .where(role_assignment.c.id == assignment_id)
                .values(role_id=auditor_id)
            )
        savepoint.rollback()
    assert _error(refused)[0] == "42501"

    # Violating: erev_owner holds every column privilege, so the DB-03 trigger answers. FORCE RLS
    # names no owner policy, hence NO FORCE inside the rolled-back transaction (SPEC-Q-129).
    ids = {"role_id": auditor_id, "id": assignment_id, "at": REVOKED_AT}
    with committed_db.owner_engine.connect() as connection:
        connection.begin()
        try:
            connection.exec_driver_sql(
                "ALTER TABLE erev.role_assignment NO FORCE ROW LEVEL SECURITY"
            )
            savepoint = connection.begin_nested()
            with pytest.raises(exc.DBAPIError) as excinfo:
                connection.execute(
                    text("UPDATE erev.role_assignment SET role_id = :role_id WHERE id = :id"), ids
                )
            savepoint.rollback()
            extended = connection.execute(
                text("UPDATE erev.role_assignment SET valid_to = :at WHERE id = :id"), ids
            )
            assert extended.rowcount == 1
        finally:
            connection.rollback()
    sqlstate, message = _error(excinfo)
    assert sqlstate == "P0001"
    assert message.startswith("EREV-TRN-001")


def test_db_03_recovery_code_used_once(committed_db: TestDatabase) -> None:
    code_id = new_id()
    with identity_session(request_id="tests-db-03-recovery") as session:
        user_id = insert_app_user(session)
        session.execute(
            insert(user_recovery_code).values(
                id=code_id, user_id=user_id, batch_id=new_id(), code_hash="$argon2id$probe"
            )
        )
    with identity_session(request_id="tests-db-03-recovery") as session:
        # Passing: used_at moves from NULL to a value.
        row = apply(
            session, "user_recovery_code", code_id, to_status=None, set_values={"used_at": USED_AT}
        )
        assert row["used_at"] == USED_AT
        # Violating in Python first: a spent code cannot be spent again.
        with pytest.raises(Problem) as spent:
            apply(
                session,
                "user_recovery_code",
                code_id,
                to_status=None,
                set_values={"used_at": USED_AT + timedelta(minutes=1)},
            )
        # Violating in the database: code_hash is not granted; used_at cannot return to NULL.
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as ungranted:
            session.execute(
                update(user_recovery_code)
                .where(user_recovery_code.c.id == code_id)
                .values(code_hash="tampered")
            )
        savepoint.rollback()
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as reset:
            session.execute(
                update(user_recovery_code)
                .where(user_recovery_code.c.id == code_id)
                .values(used_at=None)
            )
        savepoint.rollback()
    assert (spent.value.slug, [error.field for error in spent.value.errors]) == (
        "invalid-transition",
        ["used_at"],
    )
    assert getattr(ungranted.value.orig, "sqlstate", None) == "42501"
    assert getattr(reset.value.orig, "sqlstate", None) == "P0001"
    assert "EREV-TRN-001: used_at of erev.user_recovery_code is already set" in str(reset.value)


def test_db_12_entity_ids_fail_closed(committed_db: TestDatabase, keyring: KeyRing) -> None:
    result = tenant_factory(keyring=keyring)
    tenant_id = tenant_id_of(result)
    assign = {
        "tenant_id": tenant_id,
        "membership_id": result.admin_membership_id,
        "role_code": "viewer",
    }
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        # Violating: an id that names no legal entity is refused (DB-12; fail closed before RFD-2).
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as excinfo:
            insert_role_assignment(session, entity_ids=(PROBE_ID,), **assign)
        savepoint.rollback()
        # Passing: an all-entities assignment names no entity.
        insert_role_assignment(session, **assign)
        count = session.execute(select(func.count()).select_from(role_assignment)).scalar_one()
    # The provisioned tenant_admin grant (04 §14.3 item 2) and the viewer assignment.
    assert count == 2
    sqlstate, message = _error(excinfo)
    assert sqlstate == "P0001"
    assert message.startswith("EREV-REF-002")


def test_db_03_file_object_update_allow_list(committed_db: TestDatabase, keyring: KeyRing) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        file_id = insert_file_object(session, tenant_id=tenant_id)
        # Passing: a retention flag changes (T-PLT-29).
        row = apply(
            session, "file_object", file_id, to_status=None, set_values={"legal_hold": True}
        )
        assert row["legal_hold"] is True
        # erev_app holds UPDATE on the allow-listed columns only, so the grant refuses sha256.
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as refused:
            session.execute(
                update(file_object).where(file_object.c.id == file_id).values(sha256="0" * 64)
            )
        savepoint.rollback()
    assert _error(refused)[0] == "42501"

    # Violating: erev_owner holds every column privilege, so the DB-03 trigger answers; DB-01 still
    # forbids DELETE (SPEC-Q-129 for NO FORCE inside the rolled-back transaction).
    ids = {"id": file_id}
    with committed_db.owner_engine.connect() as connection:
        connection.begin()
        try:
            connection.exec_driver_sql("ALTER TABLE erev.file_object NO FORCE ROW LEVEL SECURITY")
            savepoint = connection.begin_nested()
            with pytest.raises(exc.DBAPIError) as excinfo:
                connection.execute(
                    text("UPDATE erev.file_object SET sha256 = repeat('0', 64) WHERE id = :id"), ids
                )
            savepoint.rollback()
            savepoint = connection.begin_nested()
            with pytest.raises(exc.DBAPIError) as deleted:
                connection.execute(text("DELETE FROM erev.file_object WHERE id = :id"), ids)
            savepoint.rollback()
            released = connection.execute(
                text("UPDATE erev.file_object SET legal_hold = false WHERE id = :id"), ids
            )
            assert released.rowcount == 1
        finally:
            connection.rollback()
    sqlstate, message = _error(excinfo)
    assert sqlstate == "P0001"
    assert message.startswith("EREV-TRN-001")
    assert _error(deleted)[1].startswith("EREV-IMM-001")


def test_ck_file_object_size_limit(committed_db: TestDatabase, keyring: KeyRing) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        # Passing: exactly 25 MiB.
        insert_file_object(session, tenant_id=tenant_id, size_bytes=26_214_400)
        savepoint = session.begin_nested()
        with pytest.raises(exc.IntegrityError) as excinfo:
            session.execute(
                insert(file_object).values(
                    **file_object_values(
                        tenant_id, purpose=FilePurpose.ATTACHMENT, size_bytes=26_214_401
                    )
                )
            )
        savepoint.rollback()
    assert getattr(excinfo.value.orig, "sqlstate", None) == "23514"
    assert "ck_file_object__size_limit" in str(excinfo.value)


def _fails(session: Session, statement: Executable) -> tuple[str | None, str]:
    """SQLSTATE and message of a statement that must fail; only its savepoint rolls back."""
    savepoint = session.begin_nested()
    with pytest.raises(exc.DBAPIError) as excinfo:
        session.execute(statement)
    savepoint.rollback()
    return _error(excinfo)


@contextmanager
def _provisioning(tenant_id: UUID, keyring: KeyRing) -> Iterator[Session]:
    """A provisioning platform session in the tenant's context, the one session that may insert a
    configuration version outside DRAFT (D-80; 04 §14.3)."""
    with platform_session(
        "provisioning", actor_user_id=None, request_id="tests-db04-provisioning", keyring=keyring
    ) as session:
        set_tenant_context(session, DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*"))
        yield session


def test_db_12_sod_rule_codes_exist(committed_db: TestDatabase, keyring: KeyRing) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        # Passing: catalogue codes.
        rule_id = insert_sod_rule(session, tenant_id=tenant_id, code="db12-valid")
        # Violating: an unknown code in function B, on insert and on update of a DRAFT rule.
        unknown = sod_rule_values(
            tenant_id, code="db12-unknown", function_b=("ssp.approve", "contract.explode")
        )
        inserted = _fails(session, insert(sod_rule).values(**unknown))
        updated = _fails(
            session,
            update(sod_rule)
            .where(sod_rule.c.id == rule_id)
            .values(function_a_permissions=["contract.explode"]),
        )
    for sqlstate, message in (inserted, updated):
        assert sqlstate == "P0001"
        assert message.startswith("EREV-REF-002: permission codes contract.explode")


def test_db_12_api_client_scopes_and_entity_ids(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        # Passing: catalogue codes without approval permissions, all entities.
        valid = api_client_values(tenant_id, scopes=["audit.read", "contract.read"])
        session.execute(insert(api_client).values(**valid))
        # Violating (CTL-037): an approval scope on insert and on update; an unknown code.
        approval = _fails(
            session,
            insert(api_client).values(
                **api_client_values(tenant_id, scopes=["contract.read", "contract.approve"])
            ),
        )
        widened = _fails(
            session,
            update(api_client)
            .where(api_client.c.id == valid["id"])
            .values(scopes=["audit.read", "period.lock"]),
        )
        unknown = _fails(
            session,
            insert(api_client).values(**api_client_values(tenant_id, scopes=["contract.explode"])),
        )
        # Violating: an id that names no legal entity is refused (DB-12; fail closed before RFD-2).
        scoped = _fails(
            session,
            insert(api_client).values(
                **api_client_values(tenant_id, is_all_entities=False, entity_ids=[PROBE_ID])
            ),
        )
        count = session.execute(select(func.count()).select_from(api_client)).scalar_one()
    assert count == 1
    assert approval == (
        "P0001",
        "EREV-REF-002: scopes contract.approve of erev.api_client are approval permissions",
    )
    assert widened == (
        "P0001",
        "EREV-REF-002: scopes period.lock of erev.api_client are approval permissions",
    )
    assert unknown == (
        "P0001",
        "EREV-REF-002: permission codes contract.explode of erev.api_client do not exist",
    )
    assert scoped[0] == "P0001"
    assert scoped[1].startswith("EREV-REF-002: entity_ids of erev.api_client")


@pytest.mark.control("CTL-034")
def test_db_04_insert_outside_draft_refused(committed_db: TestDatabase, keyring: KeyRing) -> None:
    provisioned = tenant_factory(keyring=keyring)
    tenant_id = tenant_id_of(provisioned)
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    at = datetime(2026, 9, 12, 14, tzinfo=UTC)

    def probes() -> list[tuple[sa.Table, dict[str, Any]]]:
        unapproved: dict[str, Any] = {"approval_request_id": None}
        return [
            (
                sod_rule,
                sod_rule_values(
                    tenant_id, code="db04-published", status=ConfigStatus.PUBLISHED, **unapproved
                ),
            ),
            (
                sod_rule,
                sod_rule_values(
                    tenant_id, code="db04-approved", status=ConfigStatus.APPROVED, **unapproved
                ),
            ),
            (
                registry_version,
                registry_version_values(
                    tenant_id,
                    status=ConfigStatus.PUBLISHED,
                    scope=RegistryScope.ENTITY,
                    entity_id=new_id(),
                    **unapproved,
                ),
            ),
        ]

    # Violating (PR-K-03): hashed inserts outside DRAFT in the tenant context, without a scope.
    with tenant_session(context) as session:
        refusals = [_fails(session, insert(table).values(**row)) for table, row in probes()]
    assert refusals == [
        ("P0001", "EREV-CFG-002: a version of erev.sod_rule is inserted as DRAFT, not PUBLISHED"),
        ("P0001", "EREV-CFG-002: a version of erev.sod_rule is inserted as DRAFT, not APPROVED"),
        (
            "P0001",
            "EREV-CFG-002: a version of erev.registry_version is inserted as DRAFT, not PUBLISHED",
        ),
    ]

    # Violating: the review probe supersedes SoD-3 v1 and inserts v2 PUBLISHED in one transaction.
    with pytest.raises(exc.DBAPIError) as excinfo, tenant_session(context) as session:
        session.execute(
            update(sod_rule)
            .where(sod_rule.c.code == "SoD-3")
            .values(status=ConfigStatus.SUPERSEDED.value, effective_to=at)
        )
        session.execute(
            insert(sod_rule).values(
                **sod_rule_values(
                    tenant_id,
                    code="SoD-3",
                    status=ConfigStatus.PUBLISHED,
                    version_no=2,
                    published_at=at,
                    approval_request_id=None,
                )
            )
        )
    assert _error(excinfo) == (
        "P0001",
        "EREV-CFG-002: a version of erev.sod_rule is inserted as DRAFT, not PUBLISHED",
    )
    with tenant_session(context, read_only=True) as session:
        combination = [
            UUID(str(value))
            for value in session.scalars(
                select(role.c.id).where(role.c.code.in_(("revenue_accountant", "revenue_reviewer")))
            )
        ]
        codes = [
            conflict.rule_code
            for conflict in conflicts_for(
                session, provisioned.admin_membership_id, adding_role_ids=combination, at=at
            )
        ]
        versions = session.execute(
            select(sod_rule.c.version_no, sod_rule.c.status).where(sod_rule.c.code == "SoD-3")
        ).all()
    assert "SoD-3" in codes
    assert [tuple(row) for row in versions] == [(1, "PUBLISHED")]

    # Passing: the same inserts inside the provisioning platform scope (04 §14.3; SPEC-Q-175).
    with _provisioning(tenant_id, keyring) as session:
        for table, row in probes():
            session.execute(insert(table).values(**row))
    with tenant_session(context, read_only=True) as session:
        inserted = session.execute(
            select(sod_rule.c.code, sod_rule.c.status)
            .where(sod_rule.c.code.in_(("db04-published", "db04-approved")))
            .order_by(sod_rule.c.code)
        ).all()
        entity_versions = session.execute(
            select(func.count())
            .select_from(registry_version)
            .where(registry_version.c.scope == RegistryScope.ENTITY.value)
        ).scalar_one()
    assert [tuple(row) for row in inserted] == [
        ("db04-approved", "APPROVED"),
        ("db04-published", "PUBLISHED"),
    ]
    assert entity_versions == 1


def test_db_04_published_sod_rule_frozen(committed_db: TestDatabase, keyring: KeyRing) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    at = datetime(2026, 9, 12, 12, tzinfo=UTC)
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        published = (
            sod_rule.c.id
            == session.execute(select(sod_rule.c.id).where(sod_rule.c.code == "SoD-3")).scalar_one()
        )
        draft_id = insert_sod_rule(session, tenant_id=tenant_id, code="db04-draft")
        draft = sod_rule.c.id == draft_id
        # Passing: a DRAFT version is editable and deletable; TESTED keeps it editable.
        session.execute(update(sod_rule).where(draft).values(function_a_permissions=["ssp.read"]))
        doomed = insert_sod_rule(session, tenant_id=tenant_id, code="db04-doomed")
        deleted = session.execute(delete(sod_rule).where(sod_rule.c.id == doomed))
        assert cast(CursorResult[Any], deleted).rowcount == 1
        session.execute(
            update(sod_rule).where(draft).values(status="TESTED", content_sha256="a" * 64)
        )
        session.execute(update(sod_rule).where(draft).values(name="Probe rule renamed"))
        row_version = session.execute(select(sod_rule.c.row_version).where(draft)).scalar_one()
        assert row_version == 4
        # Passing: a PUBLISHED version changes its lifecycle columns only.
        savepoint = session.begin_nested()
        superseded = session.execute(
            update(sod_rule).where(published).values(status="SUPERSEDED", effective_to=at)
        )
        assert cast(CursorResult[Any], superseded).rowcount == 1
        savepoint.rollback()

        # Violating: frozen columns, deletion, lifecycle pairs, approval, content hash, overlap.
        frozen = _fails(
            session,
            update(sod_rule).where(published).values(function_a_permissions=["contract.create"]),
        )
        undeletable = _fails(session, delete(sod_rule).where(published))
        skipped = _fails(session, update(sod_rule).where(draft).values(status="PUBLISHED"))
        savepoint = session.begin_nested()
        session.execute(update(sod_rule).where(draft).values(status="SUBMITTED"))
        unapproved = _fails(session, update(sod_rule).where(draft).values(status="APPROVED"))
        savepoint.rollback()
    # Only provisioning inserts outside DRAFT (D-80), so the hash and overlap probes run there.
    with _provisioning(tenant_id, keyring) as session:
        unhashed = _fails(
            session,
            insert(sod_rule).values(
                **sod_rule_values(tenant_id, code="db04-unhashed", status=ConfigStatus.TESTED)
                | {"content_sha256": None}
            ),
        )
        overlap = sod_rule_values(
            tenant_id, code="SoD-3", status=ConfigStatus.PUBLISHED, version_no=2, effective_from=at
        )
        overlapping = _fails(session, insert(sod_rule).values(**overlap))
    for sqlstate, message in (frozen, undeletable, skipped, unapproved, unhashed):
        assert sqlstate == "P0001"
        assert message.startswith("EREV-CFG-002"), message
    assert "function_a_permissions" in frozen[1]
    assert "cannot change from TESTED to PUBLISHED" in skipped[1]
    assert "needs an APPROVED approval request" in unapproved[1]
    assert overlapping[0] == "P0001"
    assert overlapping[1].startswith("EREV-CFG-001")


def test_db_04_published_overlap_rejected(committed_db: TestDatabase, keyring: KeyRing) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    at = datetime(2026, 9, 12, 13, tzinfo=UTC)
    published: dict[str, Any] = {"status": ConfigStatus.PUBLISHED, "published_at": at}
    # Only provisioning inserts PUBLISHED versions (D-80), so the ranges are probed there.
    with _provisioning(tenant_id, keyring) as session:
        # Violating: a second PUBLISHED TENANT PLATFORM version while provisioning's DEFAULT
        # version is in force without an end.
        concurrent = _fails(
            session,
            insert(registry_version).values(
                **registry_version_values(tenant_id, effective_from=at, **published)
            ),
        )
        # Passing: versions of other scope keys never overlap it.
        for scope_key in (
            {"scope": RegistryScope.BOOK, "book_code": BookCode.IFRS15},
            {"scope": RegistryScope.ENTITY, "entity_id": new_id()},
            {"scope": RegistryScope.ENTITY, "entity_id": new_id()},
        ):
            session.execute(
                insert(registry_version).values(
                    **registry_version_values(tenant_id, version_no=1, **scope_key, **published)
                )
            )
        # Passing: once the DEFAULT version ends at `at`, a version from `at` publishes.
        session.execute(
            update(registry_version)
            .where(
                registry_version.c.category == "PLATFORM",
                registry_version.c.preset_code == "DEFAULT",
            )
            .values(status=ConfigStatus.SUPERSEDED.value, effective_to=at)
        )
        session.execute(
            insert(registry_version).values(
                **registry_version_values(tenant_id, version_no=2, effective_from=at, **published)
            )
        )
        # Violating: a range reaching into the published one.
        late = _fails(
            session,
            insert(registry_version).values(
                **registry_version_values(
                    tenant_id,
                    version_no=3,
                    effective_from=at - timedelta(hours=2),
                    effective_to=at + timedelta(hours=1),
                    **published,
                )
            ),
        )
    for sqlstate, message in (concurrent, late):
        assert sqlstate == "P0001"
        assert message.startswith("EREV-CFG-001"), message


def test_db_04_fx_rate_child_frozen_after_submit(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-04 with T-REF-12 (RFD-3): rates of a DRAFT version change; once the version leaves DRAFT
    # and TESTED they are frozen.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        set_row = fx_rate_set_values(tenant_id)
        session.execute(insert(fx_rate_set).values(**set_row))
        version = fx_rate_set_version_values(tenant_id, fx_rate_set_id=set_row["id"])
        session.execute(insert(fx_rate_set_version).values(**version))
        # Passing: rates of the DRAFT version are inserted, edited and deleted.
        kept = fx_rate_values(tenant_id, fx_rate_set_version_id=version["id"])
        session.execute(insert(fx_rate).values(**kept))
        editable = fx_rate.c.id == kept["id"]
        session.execute(update(fx_rate).where(editable).values(rate=Decimal("1.106")))
        doomed = fx_rate_values(
            tenant_id, fx_rate_set_version_id=version["id"], base_currency="GBP"
        )
        session.execute(insert(fx_rate).values(**doomed))
        deleted = session.execute(delete(fx_rate).where(fx_rate.c.id == doomed["id"]))
        assert cast(CursorResult[Any], deleted).rowcount == 1
        # Submission walks DRAFT → TESTED → SUBMITTED (E-12; D-80).
        where = fx_rate_set_version.c.id == version["id"]
        session.execute(
            update(fx_rate_set_version)
            .where(where)
            .values(status=ConfigStatus.TESTED.value, content_sha256="d" * 64, rate_count=1)
        )
        session.execute(
            update(fx_rate_set_version).where(where).values(status=ConfigStatus.SUBMITTED.value)
        )
        # Violating: inserting into, editing and deleting rates of the SUBMITTED version.
        inserted = _fails(
            session,
            insert(fx_rate).values(
                **fx_rate_values(
                    tenant_id, fx_rate_set_version_id=version["id"], base_currency="JPY"
                )
            ),
        )
        edited = _fails(session, update(fx_rate).where(editable).values(rate=Decimal("1.2")))
        removed = _fails(session, delete(fx_rate).where(editable))
    frozen = (
        "P0001",
        f"EREV-CFG-002: rows of erev.fx_rate cannot change while fx_rate_set_version "
        f"{version['id']} is SUBMITTED",
    )
    assert inserted == edited == removed == frozen


def test_db_04_mapping_rule_frozen_after_submit(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-04 with T-REF-15 (RFD-7): rules of a DRAFT version change; once the version leaves DRAFT
    # and TESTED they are frozen.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        account = gl_account_values(tenant_id)
        session.execute(insert(gl_account).values(**account))
        version = account_mapping_version_values(tenant_id)
        session.execute(insert(account_mapping_version).values(**version))

        def rule_row(role: AccountRole = AccountRole.CONTRACT_LIABILITY) -> dict[str, Any]:
            return account_mapping_rule_values(
                tenant_id,
                account_mapping_version_id=version["id"],
                gl_account_id=account["id"],
                account_role=role,
            )

        # Passing: rules of the DRAFT version are inserted, edited and deleted.
        kept = rule_row()
        session.execute(insert(account_mapping_rule).values(**kept))
        editable = account_mapping_rule.c.id == kept["id"]
        session.execute(update(account_mapping_rule).where(editable).values(priority=5))
        doomed = rule_row(AccountRole.REVENUE)
        session.execute(insert(account_mapping_rule).values(**doomed))
        deleted = session.execute(
            delete(account_mapping_rule).where(account_mapping_rule.c.id == doomed["id"])
        )
        assert cast(CursorResult[Any], deleted).rowcount == 1
        # Submission walks DRAFT → TESTED → SUBMITTED (E-12).
        where = account_mapping_version.c.id == version["id"]
        session.execute(
            update(account_mapping_version)
            .where(where)
            .values(status=ConfigStatus.TESTED.value, content_sha256="e" * 64)
        )
        session.execute(
            update(account_mapping_version).where(where).values(status=ConfigStatus.SUBMITTED.value)
        )
        # Violating: inserting a rule into, editing and deleting rules of the SUBMITTED version.
        inserted = _fails(
            session, insert(account_mapping_rule).values(**rule_row(AccountRole.REVENUE))
        )
        edited = _fails(session, update(account_mapping_rule).where(editable).values(priority=6))
        removed = _fails(session, delete(account_mapping_rule).where(editable))
    frozen = (
        "P0001",
        f"EREV-CFG-002: rows of erev.account_mapping_rule cannot change while "
        f"account_mapping_version {version['id']} is SUBMITTED",
    )
    assert inserted == edited == removed == frozen


def test_t_ref_15_mapping_rule_checks(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # T-REF-15 (RFD-7): reserved roles accept no rule, BILLING_CLEARING and only it names a purpose,
    # a rule keys on a product or a revenue category, and specificity is generated (entity 8, book
    # 4, product or category 2).
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        calendar_row = fiscal_calendar_values(tenant_id)
        session.execute(insert(fiscal_calendar).values(**calendar_row))
        entity_row = legal_entity_values(tenant_id, calendar_id=calendar_row["id"])
        session.execute(insert(legal_entity).values(**entity_row))
        account = gl_account_values(tenant_id)
        session.execute(insert(gl_account).values(**account))
        version = account_mapping_version_values(tenant_id)
        session.execute(insert(account_mapping_version).values(**version))

        def values(**extra: Any) -> dict[str, Any]:
            return account_mapping_rule_values(
                tenant_id,
                account_mapping_version_id=version["id"],
                gl_account_id=account["id"],
                **extra,
            )

        passing = {
            "any": values(),
            "entity_book": values(entity_id=entity_row["id"], book_code=BookCode.ASC606.value),
            "entity_category": values(
                account_role=AccountRole.REVENUE,
                entity_id=entity_row["id"],
                revenue_category="PRODUCT",
            ),
            "clearing_book": values(
                account_role=AccountRole.BILLING_CLEARING,
                clearing_purpose=ClearingPurpose.UNAPPLIED_CASH,
                book_code=BookCode.IFRS15.value,
            ),
        }
        for row in passing.values():
            session.execute(insert(account_mapping_rule).values(**row))
        generated = {
            UUID(str(rule_id)): int(specificity)
            for rule_id, specificity in session.execute(
                select(account_mapping_rule.c.id, account_mapping_rule.c.specificity)
            )
        }
        failures = {
            "reserved": _fails(
                session,
                insert(account_mapping_rule).values(
                    **values(account_role=AccountRole.RETAINED_EARNINGS)
                ),
            ),
            "no_purpose": _fails(
                session,
                insert(account_mapping_rule).values(
                    **values(account_role=AccountRole.BILLING_CLEARING)
                ),
            ),
            "other_purpose": _fails(
                session,
                insert(account_mapping_rule).values(
                    **values(
                        account_role=AccountRole.REVENUE, clearing_purpose=ClearingPurpose.BILLING
                    )
                ),
            ),
            "product_category": _fails(
                session,
                insert(account_mapping_rule).values(
                    **values(product_id=PROBE_ID, revenue_category="PRODUCT")
                ),
            ),
            "written_specificity": _fails(
                session, insert(account_mapping_rule).values(**values(specificity=14))
            ),
        }
    assert {name: generated[row["id"]] for name, row in passing.items()} == {
        "any": 0,
        "entity_book": 12,
        "entity_category": 10,
        "clearing_book": 4,
    }
    states = {name: state for name, (state, _) in failures.items()}
    assert states == {
        "reserved": "23514",
        "no_purpose": "23514",
        "other_purpose": "23514",
        "product_category": "23514",
        "written_specificity": "428C9",
    }
    constraints = {name: message.rsplit('"', 2)[-2] for name, (_, message) in failures.items()}
    assert {
        name: constraints[name]
        for name in ("reserved", "no_purpose", "other_purpose", "product_category")
    } == {
        "reserved": "ck_account_mapping_rule__reserved_role",
        "no_purpose": "ck_account_mapping_rule__clearing_purpose",
        "other_purpose": "ck_account_mapping_rule__clearing_purpose",
        "product_category": "ck_account_mapping_rule__product_category",
    }


def test_db_04_ssp_entry_frozen_outside_draft(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DB-04 with T-REF-30 and T-REF-31 (RFD-12): entries and bands of a DRAFT version change; once
    # the version is SUBMITTED, inserting, editing or deleting either raises EREV-CFG-002. A band
    # reaches its version through its entry (tg_ssp_range__config_child).
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        book_row = ssp_book_values(tenant_id)
        session.execute(insert(ssp_book).values(**book_row))
        version = ssp_book_version_values(tenant_id, ssp_book_id=book_row["id"])
        session.execute(insert(ssp_book_version).values(**version))
        item = product_values(tenant_id)
        session.execute(insert(product_table).values(**item))

        def entry_row(**extra: Any) -> dict[str, Any]:
            return ssp_entry_values(
                tenant_id, ssp_book_version_id=version["id"], product_id=item["id"], **extra
            )

        kept = entry_row()
        session.execute(insert(ssp_entry).values(**kept))
        band = ssp_range_values(tenant_id, ssp_entry_id=kept["id"])
        session.execute(insert(ssp_range).values(**band))
        # Passing: an entry and its band of the DRAFT version are inserted, edited and deleted.
        spare = entry_row(stratification="SPARE")
        session.execute(insert(ssp_entry).values(**spare))
        spare_band = ssp_range_values(tenant_id, ssp_entry_id=spare["id"])
        session.execute(insert(ssp_range).values(**spare_band))
        session.execute(
            update(ssp_range)
            .where(ssp_range.c.id == spare_band["id"])
            .values(point_value=Decimal("120"))
        )
        session.execute(update(ssp_entry).where(ssp_entry.c.id == spare["id"]).values(region="EU"))
        session.execute(delete(ssp_range).where(ssp_range.c.id == spare_band["id"]))
        deleted = session.execute(delete(ssp_entry).where(ssp_entry.c.id == spare["id"]))
        assert cast(CursorResult[Any], deleted).rowcount == 1
        # Submission walks DRAFT → TESTED → SUBMITTED (E-12).
        where = ssp_book_version.c.id == version["id"]
        session.execute(
            update(ssp_book_version)
            .where(where)
            .values(status=ConfigStatus.TESTED.value, content_sha256="e" * 64)
        )
        session.execute(
            update(ssp_book_version).where(where).values(status=ConfigStatus.SUBMITTED.value)
        )
        # Violating: entries and bands of the SUBMITTED version.
        kept_entry = ssp_entry.c.id == kept["id"]
        kept_band = ssp_range.c.id == band["id"]
        entries = (
            _fails(session, insert(ssp_entry).values(**entry_row(stratification="LATE"))),
            _fails(session, update(ssp_entry).where(kept_entry).values(region="EU")),
            _fails(session, delete(ssp_entry).where(kept_entry)),
        )
        late_band = ssp_range_values(
            tenant_id, ssp_entry_id=kept["id"], band_dimension="QUANTITY", band_from=Decimal("10")
        )
        bands = (
            _fails(session, insert(ssp_range).values(**late_band)),
            _fails(session, update(ssp_range).where(kept_band).values(point_value=Decimal("90"))),
            _fails(session, delete(ssp_range).where(kept_band)),
        )

    def frozen(table: str) -> tuple[str, str]:
        return (
            "P0001",
            f"EREV-CFG-002: rows of erev.{table} cannot change while "
            f"ssp_book_version {version['id']} is SUBMITTED",
        )

    assert entries == (frozen("ssp_entry"),) * 3
    assert bands == (frozen("ssp_range"),) * 3


def test_t_ref_30_ssp_book_entry_and_range_checks(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # T-REF-28 to T-REF-31 (RFD-12): the column checks of books, versions, entries and bands, the
    # entry key (an absent dimension key equals a blank one) and the band key.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        book_row = ssp_book_values(tenant_id)
        session.execute(insert(ssp_book).values(**book_row))
        version = ssp_book_version_values(tenant_id, ssp_book_id=book_row["id"])
        session.execute(insert(ssp_book_version).values(**version))
        item = product_values(tenant_id)
        session.execute(insert(product_table).values(**item))

        def entry_row(**extra: Any) -> dict[str, Any]:
            return ssp_entry_values(
                tenant_id, ssp_book_version_id=version["id"], product_id=item["id"], **extra
            )

        kept = entry_row()
        session.execute(insert(ssp_entry).values(**kept))
        legacy = entry_row(
            stratification="LEGACY",
            method="legacy_range",
            unit_list_price=Decimal("120"),
            midpoint_discount_ratio=Decimal("0.25"),
            range_ratio=Decimal("0.15"),
        )
        session.execute(insert(ssp_entry).values(**legacy))
        band = ssp_range_values(tenant_id, ssp_entry_id=kept["id"])
        session.execute(insert(ssp_range).values(**band))

        def band_row(**extra: Any) -> dict[str, Any]:
            return ssp_range_values(tenant_id, ssp_entry_id=kept["id"], **extra)

        failures = {
            "book_mode": _fails(
                session, insert(ssp_book).values(**ssp_book_values(tenant_id, resolution_mode="X"))
            ),
            "sc_v_dates": _fails(
                session,
                update(ssp_book_version)
                .where(ssp_book_version.c.id == version["id"])
                .values(effective_from=datetime(2026, 1, 1, tzinfo=UTC)),
            ),
            "effective_dates": _fails(
                session,
                update(ssp_book_version)
                .where(ssp_book_version.c.id == version["id"])
                .values(effective_to_date=date(2025, 12, 31)),
            ),
            "legacy": _fails(
                session,
                insert(ssp_entry).values(
                    **entry_row(stratification="L2", method="legacy_range", range_ratio=Decimal(0))
                ),
            ),
            "discount": _fails(
                session,
                insert(ssp_entry).values(
                    **entry_row(stratification="D", midpoint_discount_ratio=Decimal(1))
                ),
            ),
            "range": _fails(
                session,
                insert(ssp_entry).values(
                    **entry_row(stratification="R", range_ratio=Decimal("-0.1"))
                ),
            ),
            "observable": _fails(
                session,
                insert(ssp_entry).values(
                    **entry_row(stratification="O", observable_point=Decimal(-1))
                ),
            ),
            "entry_key": _fails(session, insert(ssp_entry).values(**entry_row(region=""))),
            "band_dimension": _fails(
                session, insert(ssp_range).values(**band_row(band_dimension="MONTHS"))
            ),
            "band_order": _fails(
                session,
                insert(ssp_range).values(
                    **band_row(
                        band_dimension="QUANTITY",
                        band_from=Decimal(1),
                        low_value=Decimal(110),
                        mid_value=Decimal(100),
                        high_value=Decimal(120),
                    )
                ),
            ),
            "band_value": _fails(
                session,
                insert(ssp_range).values(
                    **band_row(
                        band_dimension="QUANTITY",
                        band_from=Decimal(2),
                        point_value=None,
                        low_value=Decimal(90),
                    )
                ),
            ),
            "band_key": _fails(session, insert(ssp_range).values(**band_row())),
        }
    states = {name: state for name, (state, _) in failures.items()}
    assert states == {
        **dict.fromkeys(failures, "23514"),
        "entry_key": "23505",
        "band_key": "23505",
    }
    constraints = {name: message.rsplit('"', 2)[-2] for name, (_, message) in failures.items()}
    assert constraints == {
        "book_mode": "ck_ssp_book__resolution_mode",
        "sc_v_dates": "ck_ssp_book_version__sc_v_dates_unused",
        "effective_dates": "ck_ssp_book_version__effective_dates",
        "legacy": "ck_ssp_entry__legacy_range",
        "discount": "ck_ssp_entry__midpoint_discount_ratio",
        "range": "ck_ssp_entry__range_ratio",
        "observable": "ck_ssp_entry__observable_point",
        "entry_key": "ux_ssp_entry__key",
        "band_dimension": "ck_ssp_range__band_dimension",
        "band_order": "ck_ssp_range__ordered",
        "band_value": "ck_ssp_range__value",
        "band_key": "ux_ssp_range__band",
    }


def test_t_ref_21_product_and_bundle_component_checks(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # T-REF-20 and T-REF-21 (RFD-9): a component differs from its bundle, has a positive quantity, a
    # known split basis and a ratio in (0, 1] that fixed percentages require, and a non-empty
    # validity; a component row is unique per bundle, component and valid_from; the foreign keys
    # reach product, including T-REF-15 account_mapping_rule.product_id.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        bundle = product_values(tenant_id, is_bundle=True)
        component = product_values(tenant_id)
        session.execute(insert(product_table).values(**bundle))
        session.execute(insert(product_table).values(**component))
        account = gl_account_values(tenant_id)
        session.execute(insert(gl_account).values(**account))
        version = account_mapping_version_values(tenant_id)
        session.execute(insert(account_mapping_version).values(**version))

        def values(day: int, **extra: Any) -> dict[str, Any]:
            row = product_bundle_component_values(
                tenant_id,
                bundle_product_id=bundle["id"],
                component_product_id=component["id"],
                valid_from=date(2026, 1, day),
            )
            return {**row, **extra}

        session.execute(
            insert(component_table).values(
                **values(1, split_basis="fixed_percentage", split_ratio=Decimal(1))
            )
        )
        session.execute(
            insert(account_mapping_rule).values(
                **account_mapping_rule_values(
                    tenant_id,
                    account_mapping_version_id=version["id"],
                    gl_account_id=account["id"],
                    account_role=AccountRole.REVENUE,
                    product_id=component["id"],
                )
            )
        )
        failures = {
            "same_product": _fails(
                session,
                insert(component_table).values(**values(2, component_product_id=bundle["id"])),
            ),
            "quantity": _fails(
                session, insert(component_table).values(**values(3, quantity_per_bundle=0))
            ),
            "split_basis": _fails(
                session, insert(component_table).values(**values(4, split_basis="even"))
            ),
            "split_ratio": _fails(
                session,
                insert(component_table).values(
                    **values(5, split_basis="fixed_percentage", split_ratio=Decimal("1.5"))
                ),
            ),
            "ratio_required": _fails(
                session,
                insert(component_table).values(**values(6, split_basis="fixed_percentage")),
            ),
            "valid_range": _fails(
                session, insert(component_table).values(**values(7, valid_to=date(2026, 1, 7)))
            ),
            "duplicate": _fails(session, insert(component_table).values(**values(1))),
            "unknown_component": _fails(
                session, insert(component_table).values(**values(8, component_product_id=PROBE_ID))
            ),
            "assurance_cost": _fails(
                session,
                insert(product_table).values(
                    **product_values(tenant_id, assurance_cost_per_unit=Decimal(-1))
                ),
            ),
            "disaggregation": _fails(
                session,
                insert(product_table).values(**product_values(tenant_id, disaggregation=["x"])),
            ),
            "mapping_product": _fails(
                session,
                insert(account_mapping_rule).values(
                    **account_mapping_rule_values(
                        tenant_id,
                        account_mapping_version_id=version["id"],
                        gl_account_id=account["id"],
                        account_role=AccountRole.REVENUE,
                        product_id=PROBE_ID,
                    )
                ),
            ),
        }
    assert {name: state for name, (state, _) in failures.items()} == {
        "same_product": "23514",
        "quantity": "23514",
        "split_basis": "23514",
        "split_ratio": "23514",
        "ratio_required": "23514",
        "valid_range": "23514",
        "duplicate": "23505",
        "unknown_component": "23503",
        "assurance_cost": "23514",
        "disaggregation": "23514",
        "mapping_product": "23503",
    }
    assert {name: message.rsplit('"', 2)[-2] for name, (_, message) in failures.items()} == {
        "same_product": "ck_product_bundle_component__distinct_products",
        "quantity": "ck_product_bundle_component__quantity",
        "split_basis": "ck_product_bundle_component__split_basis",
        "split_ratio": "ck_product_bundle_component__split_ratio",
        "ratio_required": "ck_product_bundle_component__split_ratio_required",
        "valid_range": "ck_product_bundle_component__valid_range",
        "duplicate": "ux_product_bundle_component__component",
        "unknown_component": "fk_product_bundle_component__component_product",
        "assurance_cost": "ck_product__assurance_cost_per_unit",
        "disaggregation": "ck_product__disaggregation",
        "mapping_product": "fk_account_mapping_rule__product",
    }


def test_t_ref_23_pob_template_version_checks(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # T-REF-22 and T-REF-23 (RFD-10): the series, increment, over-time criterion, point-in-time
    # method, ratable convention, date rule, term and JSON object checks; the version number key;
    # the foreign keys to pob_template, including T-REF-20 product.default_pob_template_id.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        template = pob_template_values(tenant_id)
        session.execute(insert(pob_template).values(**template))

        def values(version_no: int, **extra: Any) -> dict[str, Any]:
            return pob_template_version_values(
                tenant_id, pob_template_id=template["id"], version_no=version_no, **extra
            )

        over_time = {
            "satisfaction_pattern": "OVER_TIME",
            "over_time_criterion": "OT_A",
            "recognition_method": "TIME_ELAPSED",
        }
        # Passing: a daily series version, and a product defaulting to the template.
        session.execute(
            insert(pob_template_version).values(
                **values(
                    1,
                    distinctness="series",
                    series_increment_unit="day",
                    ratable_convention="DAILY",
                    **over_time,
                )
            )
        )
        session.execute(
            insert(product_table).values(
                **product_values(tenant_id, default_pob_template_id=template["id"])
            )
        )

        def fails(**row: Any) -> tuple[str | None, str]:
            return _fails(session, insert(pob_template_version).values(**row))

        failures = {
            "series": fails(**values(2, distinctness="series")),
            "increment_unit": fails(
                **values(3, distinctness="series", series_increment_unit="week")
            ),
            "criterion": fails(
                **values(4, satisfaction_pattern="OVER_TIME", recognition_method="COST_TO_COST")
            ),
            "point_in_time": fails(**values(5, recognition_method="COST_TO_COST")),
            "convention": fails(**values(6, **over_time)),
            "start_rule": fails(**values(7, start_date_rule="SIGNATURE")),
            "end_rule": fails(**values(8, end_date_rule="FOREVER")),
            "term": fails(**values(9, end_date_rule="START_PLUS_TERM")),
            "disaggregation": fails(**values(10, disaggregation=["x"])),
            "overrides": fails(**values(11, account_role_overrides=["x"])),
            "policy_values": fails(**values(12, policy_values="x")),
            "duplicate": fails(**values(1)),
            "unknown_template": fails(
                **pob_template_version_values(tenant_id, pob_template_id=PROBE_ID)
            ),
            "product_template": _fails(
                session,
                insert(product_table).values(
                    **product_values(tenant_id, default_pob_template_id=PROBE_ID)
                ),
            ),
        }
    assert {name: state for name, (state, _) in failures.items()} == {
        **dict.fromkeys(
            [
                "series",
                "increment_unit",
                "criterion",
                "point_in_time",
                "convention",
                "start_rule",
                "end_rule",
                "term",
                "disaggregation",
                "overrides",
                "policy_values",
            ],
            "23514",
        ),
        "duplicate": "23505",
        "unknown_template": "23503",
        "product_template": "23503",
    }
    assert {name: message.rsplit('"', 2)[-2] for name, (_, message) in failures.items()} == {
        "series": "ck_pob_template_version__series",
        "increment_unit": "ck_pob_template_version__series_increment_unit",
        "criterion": "ck_pob_template_version__over_time_criterion",
        "point_in_time": "ck_pob_template_version__point_in_time_method",
        "convention": "ck_pob_template_version__ratable_convention",
        "start_rule": "ck_pob_template_version__start_date_rule",
        "end_rule": "ck_pob_template_version__end_date_rule",
        "term": "ck_pob_template_version__term_months",
        "disaggregation": "ck_pob_template_version__disaggregation",
        "overrides": "ck_pob_template_version__account_role_overrides",
        "policy_values": "ck_pob_template_version__policy_values",
        "duplicate": "ux_pob_template_version__no",
        "unknown_template": "fk_pob_template_version__pob_template",
        "product_template": "fk_product__default_pob_template",
    }


def test_db_04_approved_ssp_version_immutable(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DB-04 with T-REF-29 (RFD-13): an APPROVED SSP book version needs an APPROVED request; then
    # only the lifecycle columns change, and effective_to_date is set once (BR-SSP-02). APPROVED
    # versions of an EFFECTIVE_DATE book never overlap (EREV-CFG-001); outside DRAFT their versions
    # need an effective_from_date. A BY_LABEL book skips the overlap rule.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        book_row = ssp_book_values(tenant_id)
        label_book = ssp_book_values(tenant_id, resolution_mode="BY_LABEL")
        session.execute(insert(ssp_book).values(**book_row))
        session.execute(insert(ssp_book).values(**label_book))

        def submitted(book_id: UUID, version_no: int, **extra: Any) -> sa.ColumnElement[bool]:
            version = ssp_book_version_values(
                tenant_id, ssp_book_id=book_id, version_no=version_no, **extra
            )
            session.execute(insert(ssp_book_version).values(**version))
            where = ssp_book_version.c.id == version["id"]
            session.execute(
                update(ssp_book_version)
                .where(where)
                .values(status=ConfigStatus.TESTED.value, content_sha256="e" * 64)
            )
            session.execute(
                update(ssp_book_version).where(where).values(status=ConfigStatus.SUBMITTED.value)
            )
            return where

        def request(number: str) -> UUID:
            return insert_approval_request(
                session,
                tenant_id=tenant_id,
                status=ApprovalRequestStatus.APPROVED,
                subject_type="SSP_BOOK_VERSION",
                request_no=f"APR-SSP{number}",
            )

        def approving(request_id: UUID) -> dict[str, Any]:
            return {"status": ConfigStatus.APPROVED.value, "approval_request_id": request_id}

        first = submitted(book_row["id"], 1)
        # Violating: APPROVED without an APPROVED approval request.
        unapproved = _fails(
            session,
            update(ssp_book_version).where(first).values(status=ConfigStatus.APPROVED.value),
        )
        session.execute(update(ssp_book_version).where(first).values(**approving(request("1"))))
        # Violating: methodology_label of the APPROVED version, and deleting it.
        frozen = _fails(
            session, update(ssp_book_version).where(first).values(methodology_label="Changed")
        )
        undeletable = _fails(session, delete(ssp_book_version).where(first))
        # Violating: approving version 2 from 2026-10-01 while version 1 has no end.
        second = submitted(book_row["id"], 2, effective_from_date=date(2026, 10, 1))
        overlap = _fails(
            session, update(ssp_book_version).where(second).values(**approving(request("2")))
        )
        # Passing: supersession ends version 1 once, then version 2 is approved.
        session.execute(
            update(ssp_book_version).where(first).values(effective_to_date=date(2026, 9, 30))
        )
        session.execute(update(ssp_book_version).where(second).values(**approving(request("3"))))
        # Violating: a second change of effective_to_date.
        twice = _fails(
            session,
            update(ssp_book_version).where(first).values(effective_to_date=date(2026, 8, 31)),
        )
        # Violating: an EFFECTIVE_DATE version leaving DRAFT without effective_from_date.
        undated = ssp_book_version_values(
            tenant_id, ssp_book_id=book_row["id"], version_no=3, effective_from_date=None
        )
        session.execute(insert(ssp_book_version).values(**undated))
        no_date = _fails(
            session,
            update(ssp_book_version)
            .where(ssp_book_version.c.id == undated["id"])
            .values(status=ConfigStatus.TESTED.value, content_sha256="e" * 64),
        )
        # Passing: two APPROVED versions of a BY_LABEL book with the same dates, one undated.
        for number, extra in (
            (1, {"legacy_version_label": "A"}),
            (2, {"legacy_version_label": "B", "effective_from_date": None}),
        ):
            labelled = submitted(label_book["id"], number, **extra)
            session.execute(
                update(ssp_book_version).where(labelled).values(**approving(request(f"L{number}")))
            )
        approved_count = session.execute(
            select(func.count())
            .select_from(ssp_book_version)
            .where(ssp_book_version.c.status == ConfigStatus.APPROVED.value)
        ).scalar_one()
    table = "erev.ssp_book_version"
    assert unapproved == (
        "P0001",
        f"EREV-CFG-002: a version of {table} needs an APPROVED approval request",
    )
    assert frozen == (
        "P0001",
        f"EREV-CFG-002: columns methodology_label of {table} cannot change in status APPROVED",
    )
    assert undeletable == (
        "P0001",
        f"EREV-CFG-002: a APPROVED version of {table} cannot be deleted",
    )
    assert overlap == (
        "P0001",
        f"EREV-CFG-001: the effective dates of version 2 of {table} overlap APPROVED version 1 of "
        "the same book",
    )
    assert twice == (
        "P0001",
        f"EREV-CFG-002: columns effective_to_date of {table} cannot change in status APPROVED",
    )
    assert no_date == (
        "P0001",
        f"EREV-CFG-002: a TESTED version of {table} needs effective_from_date, because its book "
        "resolves by effective date",
    )
    assert approved_count == 4


def test_db_05_ssp_book_scope_frozen_after_approval(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-05 with T-REF-28 (RFD-13): the scope columns and resolution mode of an SSP book change
    # while no version is APPROVED; afterwards they raise EREV-REF-001, while the name changes.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        book_row = ssp_book_values(tenant_id)
        session.execute(insert(ssp_book).values(**book_row))
        book = ssp_book.c.id == book_row["id"]
        version = ssp_book_version_values(tenant_id, ssp_book_id=book_row["id"])
        session.execute(insert(ssp_book_version).values(**version))
        # Passing: the scope changes while the only version is DRAFT.
        session.execute(update(ssp_book).where(book).values(currency="USD", channel="direct"))
        where = ssp_book_version.c.id == version["id"]
        session.execute(
            update(ssp_book_version)
            .where(where)
            .values(status=ConfigStatus.TESTED.value, content_sha256="e" * 64)
        )
        session.execute(
            update(ssp_book_version).where(where).values(status=ConfigStatus.SUBMITTED.value)
        )
        request_id = insert_approval_request(
            session,
            tenant_id=tenant_id,
            status=ApprovalRequestStatus.APPROVED,
            subject_type="SSP_BOOK_VERSION",
            request_no="APR-SSPDB05",
        )
        session.execute(
            update(ssp_book_version)
            .where(where)
            .values(status=ConfigStatus.APPROVED.value, approval_request_id=request_id)
        )
        # Passing: the name of a book with an APPROVED version.
        session.execute(update(ssp_book).where(book).values(name="Renamed SSP book"))
        # Violating: the currency, channel and resolution mode.
        currency = _fails(session, update(ssp_book).where(book).values(currency="EUR"))
        channel = _fails(session, update(ssp_book).where(book).values(channel=None))
        mode = _fails(session, update(ssp_book).where(book).values(resolution_mode="BY_LABEL"))
    frozen = (
        "P0001",
        f"EREV-REF-001: the scope of SSP book {book_row['code']} of erev.ssp_book is frozen: a "
        "version is approved",
    )
    assert (currency, channel, mode) == (frozen, frozen, frozen)


def test_db_05_product_code_frozen_once_referenced(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-05 with T-REF-20 (revision 0115; lane ENG-FX, item PRODUCT-CODE-FREEZE-1): the code of a
    # product changes while nothing references it; an SSP entry, an account mapping rule and an
    # obligation (a contract line) each freeze it (EREV-REF-001), while its name still changes.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")

    def recoded(product_id: Any, code: str) -> Executable:
        return update(product_table).where(product_table.c.id == product_id).values(code=code)

    with tenant_session(context) as session:
        # Passing: a product nothing references takes a new code.
        unused = product_values(tenant_id)
        session.execute(insert(product_table).values(**unused))
        free = session.execute(recoded(unused["id"], "PROBE-RECODED"))
        assert cast(CursorResult[Any], free).rowcount == 1
        # An SSP entry.
        book_row = ssp_book_values(tenant_id)
        session.execute(insert(ssp_book).values(**book_row))
        version = ssp_book_version_values(tenant_id, ssp_book_id=book_row["id"])
        session.execute(insert(ssp_book_version).values(**version))
        priced = product_values(tenant_id)
        session.execute(insert(product_table).values(**priced))
        session.execute(
            insert(ssp_entry).values(
                **ssp_entry_values(
                    tenant_id, ssp_book_version_id=version["id"], product_id=priced["id"]
                )
            )
        )
        # An account mapping rule.
        account = gl_account_values(tenant_id)
        session.execute(insert(gl_account).values(**account))
        mapping = account_mapping_version_values(tenant_id)
        session.execute(insert(account_mapping_version).values(**mapping))
        mapped = product_values(tenant_id)
        session.execute(insert(product_table).values(**mapped))
        session.execute(
            insert(account_mapping_rule).values(
                **account_mapping_rule_values(
                    tenant_id,
                    account_mapping_version_id=mapping["id"],
                    gl_account_id=account["id"],
                    account_role=AccountRole.REVENUE,
                    product_id=mapped["id"],
                )
            )
        )
        # An obligation: the line of a contract (a version of price 0 needs no allocation, DB-17).
        rows = insert_version_rows(session, tenant_id, transaction_price=Decimal("0"))
        insert_obligation_rows(session, tenant_id, rows)
        sold_id = session.execute(
            select(obligation.c.product_id).where(obligation.c.tenant_id == tenant_id)
        ).scalar_one()
        sold_code = session.execute(
            select(product_table.c.code).where(product_table.c.id == sold_id)
        ).scalar_one()
        in_use = [
            (priced["id"], priced["code"]),
            (mapped["id"], mapped["code"]),
            (sold_id, sold_code),
        ]
        failures = [
            _fails(session, recoded(product_id, f"PROBE-{index}"))
            for index, (product_id, _) in enumerate(in_use)
        ]
        # Passing: the name of a product in use.
        named = session.execute(
            update(product_table)
            .where(product_table.c.id == priced["id"])
            .values(name="Renamed product")
        )
        assert cast(CursorResult[Any], named).rowcount == 1
    assert failures == [
        (
            "P0001",
            f"EREV-REF-001: the code of product {code} of erev.product is frozen: a contract "
            "line, an SSP entry or an account mapping rule references the product",
        )
        for _, code in in_use
    ]


def test_db_04_approved_fx_version_immutable(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DB-04 with T-REF-11 (RFD-3): APPROVED is the effective state of an FX rate set version; it
    # needs an APPROVED request, and afterwards only the lifecycle columns change.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    at = datetime(2026, 9, 12, 15, tzinfo=UTC)
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        set_row = fx_rate_set_values(tenant_id)
        session.execute(insert(fx_rate_set).values(**set_row))

        def submitted(version_no: int) -> sa.ColumnElement[bool]:
            version = fx_rate_set_version_values(
                tenant_id, fx_rate_set_id=set_row["id"], version_no=version_no
            )
            session.execute(insert(fx_rate_set_version).values(**version))
            where = fx_rate_set_version.c.id == version["id"]
            session.execute(
                update(fx_rate_set_version)
                .where(where)
                .values(status=ConfigStatus.TESTED.value, content_sha256="e" * 64)
            )
            session.execute(
                update(fx_rate_set_version).where(where).values(status=ConfigStatus.SUBMITTED.value)
            )
            return where

        def approve(where: sa.ColumnElement[bool], version_no: int) -> None:
            request_id = insert_approval_request(
                session,
                tenant_id=tenant_id,
                status=ApprovalRequestStatus.APPROVED,
                subject_type="FX_RATE_SET_VERSION",
                request_no=f"APR-FX{version_no}",
            )
            session.execute(
                update(fx_rate_set_version)
                .where(where)
                .values(
                    status=ConfigStatus.APPROVED.value,
                    approval_request_id=request_id,
                    published_at=at,
                )
            )

        first = submitted(1)
        # Violating: APPROVED without an APPROVED approval request.
        unapproved = _fails(
            session,
            update(fx_rate_set_version).where(first).values(status=ConfigStatus.APPROVED.value),
        )
        approve(first, 1)
        # Passing: a second APPROVED version over the same coverage (the highest one wins,
        # T-REF-11), and a lifecycle column of an APPROVED version.
        approve(submitted(2), 2)
        session.execute(update(fx_rate_set_version).where(first).values(published_by=new_id()))
        # Violating: coverage_to of the APPROVED version, and deleting it.
        changed = _fails(
            session,
            update(fx_rate_set_version).where(first).values(coverage_to=date(2026, 10, 31)),
        )
        undeletable = _fails(session, delete(fx_rate_set_version).where(first))
        approved = session.execute(
            select(func.count())
            .select_from(fx_rate_set_version)
            .where(fx_rate_set_version.c.status == ConfigStatus.APPROVED.value)
        ).scalar_one()
    assert unapproved == (
        "P0001",
        "EREV-CFG-002: a version of erev.fx_rate_set_version needs an APPROVED approval request",
    )
    assert changed == (
        "P0001",
        "EREV-CFG-002: columns coverage_to of erev.fx_rate_set_version cannot change in status "
        "APPROVED",
    )
    assert undeletable == (
        "P0001",
        "EREV-CFG-002: a APPROVED version of erev.fx_rate_set_version cannot be deleted",
    )
    assert approved == 2


def test_db_04_rule_child_frozen(committed_db: TestDatabase, keyring: KeyRing) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        set_row = rule_set_values(tenant_id)
        session.execute(insert(rule_set).values(**set_row))
        draft = rule_set_version_values(tenant_id, rule_set_id=set_row["id"])
        submitted = rule_set_version_values(tenant_id, rule_set_id=set_row["id"], version_no=2)
        for version in (draft, submitted):
            session.execute(insert(rule_set_version).values(**version))
        # A version is inserted DRAFT and leaves DRAFT along E-12 (D-80).
        submitted_version = rule_set_version.c.id == submitted["id"]
        session.execute(
            update(rule_set_version)
            .where(submitted_version)
            .values(status=ConfigStatus.TESTED.value, content_sha256="c" * 64)
        )
        session.execute(
            update(rule_set_version)
            .where(submitted_version)
            .values(status=ConfigStatus.SUBMITTED.value)
        )
        # Passing: rules and test cases of a DRAFT version are inserted, edited and deleted.
        draft_rule = rule_values(tenant_id, rule_set_version_id=draft["id"])
        session.execute(insert(rule).values(**draft_rule))
        editable = rule.c.id == draft_rule["id"]
        session.execute(update(rule).where(editable).values(priority=5))
        case = rule_test_case_values(tenant_id, subject_id=draft["id"])
        session.execute(insert(rule_test_case).values(**case))
        session.execute(
            update(rule_test_case)
            .where(rule_test_case.c.id == case["id"])
            .values(last_result="PASS")
        )
        doomed = rule_values(tenant_id, rule_set_version_id=draft["id"], rule_key="DOOMED")
        session.execute(insert(rule).values(**doomed))
        deleted = session.execute(delete(rule).where(rule.c.id == doomed["id"]))
        assert cast(CursorResult[Any], deleted).rowcount == 1

        # Violating: children of a SUBMITTED version, of a missing parent table, of a version that
        # left TESTED, and of the provisioned PUBLISHED AUTO-BOOTSTRAP version.
        into_submitted = _fails(
            session,
            insert(rule).values(**rule_values(tenant_id, rule_set_version_id=submitted["id"])),
        )
        case_submitted = _fails(
            session,
            insert(rule_test_case).values(
                **rule_test_case_values(tenant_id, subject_id=submitted["id"])
            ),
        )
        missing_parent = _fails(
            session,
            insert(rule_test_case).values(
                **rule_test_case_values(
                    tenant_id, subject_id=new_id(), subject_type="pob_template_version"
                )
            ),
        )
        draft_version = rule_set_version.c.id == draft["id"]
        session.execute(
            update(rule_set_version)
            .where(draft_version)
            .values(status=ConfigStatus.TESTED.value, content_sha256="b" * 64)
        )
        session.execute(
            update(rule_set_version)
            .where(draft_version)
            .values(status=ConfigStatus.SUBMITTED.value)
        )
        edited = _fails(session, update(rule).where(editable).values(priority=6))
        removed = _fails(session, delete(rule).where(editable))
        bootstrap = _fails(
            session,
            update(rule)
            .where(rule.c.rule_key == "AUTO-BOOTSTRAP")
            .values(outputs={"auto_approve": False}),
        )
    for sqlstate, message in (
        into_submitted,
        case_submitted,
        missing_parent,
        edited,
        removed,
        bootstrap,
    ):
        assert sqlstate == "P0001"
        assert message.startswith("EREV-CFG-002"), message
    assert f"while rule_set_version {submitted['id']} is SUBMITTED" in into_submitted[1]
    assert "pob_template_version" in missing_parent[1]
    assert missing_parent[1].endswith("is not visible")
    assert "is PUBLISHED" in bootstrap[1]


def test_sod_exception_validity_limit(committed_db: TestDatabase, keyring: KeyRing) -> None:
    result = tenant_factory(keyring=keyring)
    tenant_id = tenant_id_of(result)
    start = datetime(2026, 9, 12, 12, tzinfo=UTC)
    ids = {"tenant_id": tenant_id, "membership_id": result.admin_membership_id}
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        # Passing: 366 days.
        insert_sod_exception(session, valid_from=start, valid_to=start + timedelta(days=366), **ids)
        # Violating: 367 days, and an empty range.
        longer = sod_exception_values(valid_from=start, valid_to=start + timedelta(days=367), **ids)
        empty = sod_exception_values(valid_from=start, valid_to=start, **ids)
        failures = [_fails(session, insert(sod_exception).values(**row)) for row in (longer, empty)]
    assert [sqlstate for sqlstate, _ in failures] == ["23514", "23514"]
    assert all("ck_sod_exception__validity" in message for _, message in failures)


def test_support_grant_validity_and_scope(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # 04 T-PLT-33: at most 72 hours, ending after the start, and scope READ_ONLY in 1.0.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    start = datetime(2026, 9, 13, 9, tzinfo=UTC)
    with identity_session(request_id="tests-support-grant-checks") as session:
        operator_id = insert_app_user(session)
    ids = {"tenant_id": tenant_id, "operator_user_id": operator_id}
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        # Passing: exactly 72 hours.
        insert_support_grant(session, valid_from=start, valid_to=start + timedelta(hours=72), **ids)
        # Violating: 72 hours and one second, an empty range, and another scope.
        longer = support_grant_values(
            valid_from=start, valid_to=start + timedelta(hours=72, seconds=1), **ids
        )
        empty = support_grant_values(valid_from=start, valid_to=start, **ids)
        wide = {**support_grant_values(**ids), "scope": "READ_WRITE"}
        failures = [
            _fails(session, insert(support_grant).values(**row)) for row in (longer, empty, wide)
        ]
    assert [sqlstate for sqlstate, _ in failures] == ["23514", "23514", "23514"]
    assert all("ck_support_grant__validity" in message for _, message in failures[:2])
    assert "ck_support_grant__scope" in failures[2][1]


def test_db_10_self_approval_trigger(committed_db: TestDatabase, keyring: KeyRing) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with identity_session(request_id="tests-db-10-users") as session:
        preparer_id, approver_id, outsider_id = (insert_app_user(session) for _ in range(3))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        for user_id in (preparer_id, approver_id):
            insert_active_membership(session, tenant_id=tenant_id, user_id=user_id)
        request_id = insert_approval_request(session, tenant_id=tenant_id, preparer_id=preparer_id)
        step_id = insert_approval_step(session, tenant_id=tenant_id, approval_request_id=request_id)

        def decision(approver: UUID, **extra: Any) -> Executable:
            values = approval_decision_values(
                tenant_id,
                approval_request_id=request_id,
                approval_step_id=step_id,
                approver_id=approver,
                **extra,
            )
            return insert(approval_decision).values(**values)

        # Violating: the preparer; a changed subject; a user without an ACTIVE membership.
        self_approval = _fails(session, decision(preparer_id))
        stale = _fails(session, decision(approver_id, subject_content_sha256="d" * 64))
        outsider = _fails(session, decision(outsider_id))
        # Passing: another member approves once.
        session.execute(decision(approver_id))
        # Violating: the same approver decides again.
        repeat = _fails(session, decision(approver_id))
    assert self_approval[0] == stale[0] == outsider[0] == repeat[0] == "P0001"
    assert self_approval[1].startswith("EREV-APR-001"), self_approval[1]
    assert stale[1].startswith("EREV-APR-003"), stale[1]
    assert outsider[1].startswith("EREV-TRN-001"), outsider[1]
    assert repeat[1].startswith("EREV-APR-002"), repeat[1]


def test_db_10_signoff_reviewer_differs_from_preparer(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-10 (CLO-2): a REVIEWER or CONTROLLER sign-off by a PREPARER signer of the same subject, and
    # a PREPARER sign-off by one of its reviewers, raise EREV-APR-001; another user, or the same
    # user on another subject, succeeds.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with identity_session(request_id="tests-db-10-signoff-users") as session:
        preparer, reviewer = (insert_app_user(session) for _ in range(2))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        parts = insert_close_parts(session, tenant_id)
        first, other = (
            reconciliation_values(tenant_id, entity_id=parts.entity_id, period_id=parts.period_id)
            for _ in range(2)
        )
        session.execute(insert(reconciliation), [first, other])

        def sign(subject: dict[str, Any], signer: UUID, role: str) -> Executable:
            values = signoff_values(
                tenant_id, subject_id=subject["id"], signer_id=signer, role=role
            )
            return insert(signoff).values(**values)

        session.execute(sign(first, preparer, "PREPARER"))
        own_review = _fails(session, sign(first, preparer, "REVIEWER"))
        own_certification = _fails(session, sign(first, preparer, "CONTROLLER"))
        session.execute(sign(first, reviewer, "REVIEWER"))
        reviewer_prepares = _fails(session, sign(first, reviewer, "PREPARER"))
        session.execute(sign(first, reviewer, "CONTROLLER"))
        session.execute(sign(other, preparer, "REVIEWER"))
        signed = session.execute(
            select(signoff.c.subject_id, signoff.c.role, signoff.c.signer_id)
        ).all()
    subject = f"reconciliation {first['id']}"
    assert own_review == (
        "P0001",
        f"EREV-APR-001: signer {preparer} of the REVIEWER sign-off of {subject} signed it as "
        "PREPARER",
    )
    assert own_certification == (
        "P0001",
        f"EREV-APR-001: signer {preparer} of the CONTROLLER sign-off of {subject} signed it as "
        "PREPARER",
    )
    assert reviewer_prepares == (
        "P0001",
        f"EREV-APR-001: signer {reviewer} of the PREPARER sign-off of {subject} signed it as "
        "REVIEWER",
    )
    assert sorted((row.subject_id, row.role, row.signer_id) for row in signed) == sorted(
        [
            (first["id"], "PREPARER", preparer),
            (first["id"], "REVIEWER", reviewer),
            (first["id"], "CONTROLLER", reviewer),
            (other["id"], "REVIEWER", preparer),
        ]
    )


def test_db_03_reconciliation_and_checklist_transitions(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-03 (CLO-2): a reconciliation moves along SM-09 and, once CERTIFIED, changes only to
    # REOPENED; its items change their explanation while it is not CERTIFIED; a checklist item moves
    # along the E-60 pairs and keeps its identity. Unlisted columns and deletes are not granted.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        parts = insert_close_parts(session, tenant_id)
        recon = reconciliation_values(
            tenant_id, entity_id=parts.entity_id, period_id=parts.period_id
        )
        session.execute(insert(reconciliation).values(**recon))
        item = reconciliation_item_values(tenant_id, reconciliation_id=recon["id"])
        session.execute(insert(reconciliation_item).values(**item))

        def reconcile(**values: Any) -> Executable:
            return update(reconciliation).where(reconciliation.c.id == recon["id"]).values(**values)

        def explain(**values: Any) -> Executable:
            target = reconciliation_item.c.id == item["id"]
            return update(reconciliation_item).where(target).values(**values)

        assert _fails(session, reconcile(status="CERTIFIED")) == (
            "P0001",
            "EREV-TRN-001: status of erev.reconciliation cannot change from DRAFT to CERTIFIED",
        )
        session.execute(explain(explanation="Invoice INV-US-1001 posted in October."))
        session.execute(reconcile(status="PREPARED", variance_count=1))
        session.execute(reconcile(status="REVIEWED"))
        session.execute(reconcile(status="CERTIFIED", certified_at=APPROVED_AT))
        assert _fails(session, reconcile(variance_count=0)) == (
            "P0001",
            "EREV-TRN-001: columns variance_count of erev.reconciliation cannot change while "
            "status is CERTIFIED",
        )
        assert _fails(session, explain(explanation="Later.")) == (
            "P0001",
            "EREV-TRN-001: erev.reconciliation_item cannot change while its reconciliation is "
            "CERTIFIED",
        )
        assert _fails(session, reconcile(kind="BILLING_TO_SUBLEDGER"))[0] == "42501"
        assert _fails(session, explain(difference=Decimal("0")))[0] == "42501"
        removed = delete(reconciliation_item).where(reconciliation_item.c.id == item["id"])
        assert _fails(session, removed)[0] == "42501"
        session.execute(reconcile(status="REOPENED"))
        # 04 T-CLS-06 rev 1.121 (revision 0095; supervisor ruling R-54 (a)): a REOPENED row is
        # history — every regeneration inserts a new DRAFT row (D-98 79) — so the pair
        # REOPENED → DRAFT is retired; the row's items still take an explanation.
        assert _fails(session, reconcile(status="DRAFT")) == (
            "P0001",
            "EREV-TRN-001: status of erev.reconciliation cannot change from REOPENED to DRAFT",
        )
        session.execute(
            explain(
                explanation="Explained on the reopened row.",
                resolved_at=APPROVED_AT,
                resolved_by_kind="SYSTEM",
            )
        )
        # Rev 1.121: the trial balance is attached once — ``source_file_id`` and ``sync_run_id``
        # are written while NULL and never changed afterwards.
        attached = reconciliation_values(
            tenant_id, entity_id=parts.entity_id, period_id=parts.period_id
        )
        session.execute(insert(reconciliation).values(**attached))
        first_file, second_file = (file_object_values(tenant_id) for _ in range(2))
        session.execute(insert(file_object).values(**first_file))
        session.execute(insert(file_object).values(**second_file))

        def attach(**values: Any) -> Executable:
            target = reconciliation.c.id == attached["id"]
            return update(reconciliation).where(target).values(**values)

        session.execute(attach(source_file_id=first_file["id"], variance_count=1))
        assert _fails(session, attach(source_file_id=second_file["id"])) == (
            "P0001",
            "EREV-TRN-001: source_file_id of erev.reconciliation is already set",
        )
        pulled = new_id()
        session.execute(attach(sync_run_id=pulled))
        assert _fails(session, attach(sync_run_id=new_id())) == (
            "P0001",
            "EREV-TRN-001: sync_run_id of erev.reconciliation is already set",
        )
        assert _fails(session, attach(as_of_known_at=APPROVED_AT))[0] == "42501"

        template = close_checklist_template_values(tenant_id)
        session.execute(insert(close_checklist_template).values(**template))
        checklist = close_checklist_item_values(
            tenant_id,
            template_id=template["id"],
            entity_id=parts.entity_id,
            period_id=parts.period_id,
        )
        session.execute(insert(close_checklist_item).values(**checklist))

        def check(**values: Any) -> Executable:
            target = close_checklist_item.c.id == checklist["id"]
            return update(close_checklist_item).where(target).values(**values)

        evaluated = {"count": 2, "detail": "Pending approvals: 2", "evaluated_at": "2026-10-01"}
        session.execute(check(status="FAILED", result=evaluated))
        session.execute(check(status="PASSED", result={**evaluated, "count": 0, "detail": None}))
        session.execute(check(status="FAILED", result=evaluated))
        session.execute(
            check(status="WAIVED", waiver_approval_request_id=parts.approval_request_id)
        )
        assert _fails(session, check(status="PASSED")) == (
            "P0001",
            "EREV-TRN-001: status of erev.close_checklist_item cannot change from WAIVED to PASSED",
        )
        assert _fails(session, check(period_id=new_id())) == (
            "P0001",
            "EREV-TRN-001: columns period_id of erev.close_checklist_item cannot change",
        )
        removed = delete(close_checklist_item).where(close_checklist_item.c.id == checklist["id"])
        assert _fails(session, removed)[0] == "42501"
    with tenant_session(context, read_only=True) as session:
        stored_recon = session.execute(
            select(reconciliation.c.status, reconciliation.c.certified_at).where(
                reconciliation.c.id == recon["id"]
            )
        ).one()
        explanation = session.execute(
            select(reconciliation_item.c.explanation).where(reconciliation_item.c.id == item["id"])
        ).scalar_one()
        stored_item = session.execute(
            select(close_checklist_item.c.status, close_checklist_item.c.row_version).where(
                close_checklist_item.c.id == checklist["id"]
            )
        ).one()
    assert str(stored_recon.status) == "REOPENED" and stored_recon.certified_at == APPROVED_AT
    assert explanation == "Explained on the reopened row."
    assert tuple(stored_item) == ("WAIVED", 5)


def test_db_10_access_review_separation_trigger(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    decided_at = datetime(2026, 9, 12, 12, tzinfo=UTC)
    with identity_session(request_id="tests-db-10-access-review-users") as session:
        member_user, reviewer_user = (insert_app_user(session) for _ in range(2))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        member_id = insert_active_membership(session, tenant_id=tenant_id, user_id=member_user)
        reviewer_id = insert_active_membership(session, tenant_id=tenant_id, user_id=reviewer_user)
        campaign = access_review_campaign_values(
            tenant_id, reviewer_membership_ids=[member_id, reviewer_id]
        )
        session.execute(insert(access_review_campaign).values(**campaign))

        def item(membership_id: UUID, reviewer: UUID | None) -> dict[str, Any]:
            return access_review_item_values(
                tenant_id,
                access_review_campaign_id=campaign["id"],
                membership_id=membership_id,
                reviewer_id=reviewer,
            )

        # Violating: an item inserted as decided by the reviewed member.
        own_insert = _fails(
            session, insert(access_review_item).values(**item(member_id, member_user))
        )
        pending = item(member_id, None)
        session.execute(insert(access_review_item).values(**pending))

        def decide(reviewer: UUID) -> Executable:
            return (
                update(access_review_item)
                .where(access_review_item.c.id == pending["id"])
                .values(decision="CERTIFIED", reviewer_id=reviewer, decided_at=decided_at)
            )

        # Violating: the reviewed member decides their own item.
        own_update = _fails(session, decide(member_user))
        # Passing: another member decides, and decides an item of the first member.
        session.execute(decide(reviewer_user))
        session.execute(insert(access_review_item).values(**item(reviewer_id, member_user)))
    assert own_insert[0] == own_update[0] == "P0001"
    assert own_insert[1].startswith("EREV-APR-001"), own_insert[1]
    assert own_update[1].startswith("EREV-APR-001"), own_update[1]


def test_db_11_attachment_void_after_approval(committed_db: TestDatabase, keyring: KeyRing) -> None:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    at = datetime(2026, 9, 12, 12, tzinfo=UTC)
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        file_id = insert_file_object(session, tenant_id=tenant_id)
        approved_subject, pending_subject = new_id(), new_id()
        insert_approval_request(
            session,
            tenant_id=tenant_id,
            subject_id=approved_subject,
            status=ApprovalRequestStatus.APPROVED,
        )
        insert_approval_request(session, tenant_id=tenant_id, subject_id=pending_subject)
        attachments: dict[UUID, UUID] = {}
        for subject_id in (approved_subject, pending_subject):
            attachments[subject_id] = new_id()
            session.execute(
                insert(file_attachment).values(
                    tenant_id=tenant_id,
                    id=attachments[subject_id],
                    file_object_id=file_id,
                    subject_type="sod_exception",
                    subject_id=subject_id,
                    created_by_kind=PrincipalKind.SYSTEM.value,
                )
            )

        def void(subject_id: UUID) -> Executable:
            return (
                update(file_attachment)
                .where(file_attachment.c.id == attachments[subject_id])
                .values(
                    voided_at=at, voided_by_kind=PrincipalKind.SYSTEM.value, void_reason="Wrong"
                )
            )

        # Passing: the request relying on the subject is still pending.
        session.execute(void(pending_subject))
        # Violating: an APPROVED request relies on the subject.
        refused = _fails(session, void(approved_subject))
    assert refused[0] == "P0001"
    assert refused[1].startswith("EREV-ATT-001"), refused[1]


def test_t_plt_21_delegation_window_check(committed_db: TestDatabase, keyring: KeyRing) -> None:
    result = tenant_factory(keyring=keyring)
    tenant_id = tenant_id_of(result)
    start = datetime(2026, 9, 12, 12, tzinfo=UTC)
    with identity_session(request_id="tests-t-plt-21-user") as session:
        delegate_user_id = insert_app_user(session)
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        delegate = insert_active_membership(session, tenant_id=tenant_id, user_id=delegate_user_id)
        ids = {
            "delegator_membership_id": result.admin_membership_id,
            "delegate_membership_id": delegate,
        }

        def delegation(days: int, **changes: UUID) -> Executable:
            values = approval_delegation_values(
                tenant_id,
                valid_from=start,
                valid_to=start + timedelta(days=days),
                **(ids | changes),
            )
            return insert(approval_delegation).values(**values)

        def starting(ahead: int, days: int) -> Executable:
            """Created at ``start``, in force ``ahead`` days later, for ``days`` days."""
            values = approval_delegation_values(
                tenant_id,
                valid_from=start + timedelta(days=ahead),
                valid_to=start + timedelta(days=ahead + days),
                **ids,
            )
            return insert(approval_delegation).values(**values, created_at=start)

        # Passing: 30 days.
        session.execute(delegation(30))
        # Violating: 91 days; a membership delegating to itself.
        longer = _fails(session, delegation(91))
        itself = _fails(session, delegation(30, delegator_membership_id=delegate))
        # 04 rev 1.189 (ruling R-111 (4); PRD BR-PLT-07): a delegation ends no later than 90 days
        # after the command that creates it; a later start does not move the end. Passing: it
        # starts in 30 days and ends on the ninetieth; violating: one day later, which the window
        # check alone admitted (61 days from its start).
        session.execute(starting(30, 60))
        late = _fails(session, starting(30, 61))
    assert longer[0] == itself[0] == late[0] == "23514"
    assert "ck_approval_delegation__validity" in longer[1]
    assert "ck_approval_delegation__distinct_memberships" in itself[1]
    assert "ck_approval_delegation__ends" in late[1]


def test_t_ref_19_external_id_unique_per_source_system(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # T-REF-19 (RFD-8; REQ-REF-010): ux_customer__code, and ux_customer__external on
    # (tenant_id, source_system, external_id) WHERE external_id IS NOT NULL.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    netsuite, salesforce = SourceSystem.NETSUITE, SourceSystem.SALESFORCE
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        first = customer_values(tenant_id, source_system=netsuite, external_id="C-DE-3001")
        session.execute(insert(customer).values(**first))
        # Customers without an external id never collide, and another source may reuse the id.
        for _ in range(2):
            session.execute(
                insert(customer).values(**customer_values(tenant_id, source_system=netsuite))
            )
        reused = customer_values(tenant_id, source_system=salesforce, external_id="C-DE-3001")
        session.execute(insert(customer).values(**reused))

        repeated = customer_values(tenant_id, source_system=netsuite, external_id="C-DE-3001")
        sqlstate, message = _fails(session, insert(customer).values(**repeated))
        assert (sqlstate, "ux_customer__external" in message) == ("23505", True), message
        same_code = customer_values(tenant_id, code=first["code"])
        sqlstate, message = _fails(session, insert(customer).values(**same_code))
        assert (sqlstate, "ux_customer__code" in message) == ("23505", True), message
        lower_country = {**customer_values(tenant_id), "country_code": "de"}
        sqlstate, message = _fails(session, insert(customer).values(**lower_country))
        assert (sqlstate, "ck_customer__country_code" in message) == ("23514", True), message

    # Another tenant's customers are keyed separately.
    other = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=other, user_id=None, entity_scope="*")) as session:
        mirror = customer_values(other, source_system=netsuite, external_id="C-DE-3001")
        session.execute(insert(customer).values(**mirror))


def test_db_08_event_stream_gap_rejected(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DB-08 (CTR-1): tg_contract_event__insert assigns record_seq and recorded_at, keeps a version
    # at or below the contract's head and after its predecessor, and copies the contract's entity
    # (EREV-EVT-001); ux_contract_event__stream refuses a repeated version.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        chain = insert_contract_rows(session, tenant_id, head_stream_version=3)
        other = insert_contract_rows(session, tenant_id)

        def event(version: int, **extra: Any) -> Executable:
            row = contract_event_values(
                tenant_id,
                contract_id=chain.contract_id,
                contracting_entity_id=chain.entity_id,
                stream_version=version,
            )
            return insert(contract_event).values(**{**row, **extra})

        supplied = datetime(2020, 1, 1, tzinfo=UTC)
        for version in (1, 2, 3):
            session.execute(event(version, recorded_at=supplied, record_seq=0))
        stored = session.execute(
            select(
                contract_event.c.stream_version,
                contract_event.c.recorded_at,
                contract_event.c.record_seq,
            )
            .where(contract_event.c.contract_id == chain.contract_id)
            .order_by(contract_event.c.stream_version)
        ).all()
        assert [row.stream_version for row in stored] == [1, 2, 3]
        # Server-assigned: never the client's values; asserted by order and presence only.
        assert all(row.recorded_at > supplied and row.record_seq > 0 for row in stored)
        assert stored[0].record_seq < stored[1].record_seq < stored[2].record_seq

        # stream_version 5 when the head is 3.
        assert _fails(session, event(5)) == (
            "P0001",
            f"EREV-EVT-001: stream_version 5 of contract {chain.contract_id} is above the head 3",
        )
        # A raised head does not admit a gap: version 5 needs version 4.
        session.execute(
            update(contract)
            .where(contract.c.id == chain.contract_id)
            .values(head_stream_version=5, updated_by_kind="SYSTEM")
        )
        assert _fails(session, event(5)) == (
            "P0001",
            f"EREV-EVT-001: stream_version 5 of contract {chain.contract_id} follows no version 4",
        )
        sqlstate, message = _fails(session, event(3))
        assert (sqlstate, "ux_contract_event__stream" in message) == ("23505", True), message
        sqlstate, message = _fails(session, event(4, contracting_entity_id=other.entity_id))
        assert (sqlstate, message.startswith("EREV-EVT-001: contracting_entity_id")) == (
            "P0001",
            True,
        ), message
        sqlstate, message = _fails(session, event(1, contract_id=new_id()))
        assert (sqlstate, message.startswith("EREV-EVT-001")) == ("P0001", True), message
        # Versions 4 and 5 in order pass.
        session.execute(event(4))
        session.execute(event(5))
        versions = select(func.count()).where(contract_event.c.contract_id == chain.contract_id)
        assert session.execute(versions).scalar_one() == 5


def test_db_18_header_change_without_event_rejected(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-18 (CTR-1): tg_contract__projection lets a contract header change only while
    # head_stream_version rises; the SC-M columns, latest_computation_id and combination_group_id
    # change without an event (EREV-CON-001).
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        chain = insert_contract_rows(session, tenant_id, head_stream_version=1)
        # CTR-2 adds fk_contract__latest_computation: the other group carries a computation.
        other = insert_version_rows(session, tenant_id)
        target = contract.c.id == chain.contract_id
        moved = update(contract).where(target).values(inception_date=date(2026, 2, 1))
        assert _fails(session, moved) == (
            "P0001",
            f"EREV-CON-001: columns inception_date of erev.contract row {chain.contract_id} "
            "change without an appended event",
        )
        # Several columns are named; a lower head is a change too.
        sqlstate, message = _fails(
            session, update(contract).where(target).values(status="ACTIVE", memo_1="Signed")
        )
        assert message.startswith("EREV-CON-001: columns memo_1, status of erev.contract"), message
        sqlstate, message = _fails(
            session, update(contract).where(target).values(head_stream_version=0)
        )
        assert message.startswith("EREV-CON-001: columns head_stream_version"), message
        # Without an event: the SC-M columns, latest_computation_id and combination_group_id.
        session.execute(
            update(contract)
            .where(target)
            .values(
                combination_group_id=other.chain.group_id,
                latest_computation_id=other.computation_id,
                row_version=contract.c.row_version + 1,
                updated_at=func.now(),
                updated_by=new_id(),
                updated_by_kind="USER",
            )
        )
        # With a raised head the header changes.
        session.execute(
            update(contract)
            .where(target)
            .values(inception_date=date(2026, 2, 1), status="ACTIVE", head_stream_version=2)
        )
        stored = session.execute(
            select(
                contract.c.inception_date, contract.c.status, contract.c.head_stream_version
            ).where(target)
        ).one()
        assert tuple(stored) == (date(2026, 2, 1), "ACTIVE", 2)


def test_db_03_contract_status_tables(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DB-03 (CTR-1): event_submission is editable while DRAFT, then changes status along T-CON-24
    # with approval_request_id, applied_event_ids and SC-M only; a membership ends once (T-CON-04);
    # a group moves along E-95 (L3-1-Q-14).
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        chain = insert_contract_rows(session, tenant_id, head_stream_version=1)
        submission = event_submission_values(
            tenant_id, contract_id=chain.contract_id, contracting_entity_id=chain.entity_id
        )
        session.execute(insert(event_submission).values(**submission))
        target = event_submission.c.id == submission["id"]
        session.execute(
            update(event_submission).where(target).values(comment="Evidence attached", events=[])
        )
        session.execute(update(event_submission).where(target).values(status="SUBMITTED"))
        assert _fails(session, update(event_submission).where(target).values(comment="Later")) == (
            "P0001",
            "EREV-TRN-001: columns comment of erev.event_submission cannot change",
        )
        assert _fails(session, update(event_submission).where(target).values(status="DRAFT")) == (
            "P0001",
            "EREV-TRN-001: status of erev.event_submission cannot change from SUBMITTED to DRAFT",
        )
        # The contract of a submission is not granted for UPDATE at all.
        assert (
            _fails(session, update(event_submission).where(target).values(contract_id=new_id()))[0]
            == "42501"
        )
        session.execute(update(event_submission).where(target).values(status="APPROVED"))
        event_id = new_id()
        session.execute(
            update(event_submission)
            .where(target)
            .values(status="APPLIED", applied_event_ids=[event_id])
        )

        event = contract_event_values(
            tenant_id,
            contract_id=chain.contract_id,
            contracting_entity_id=chain.entity_id,
            stream_version=1,
        )
        session.execute(insert(contract_event).values(**event))
        membership = combination_group_member_values(
            tenant_id,
            combination_group_id=chain.group_id,
            contract_id=chain.contract_id,
            join_event_id=event["id"],
        )
        session.execute(insert(combination_group_member).values(**membership))
        ended = combination_group_member.c.id == membership["id"]
        session.execute(
            update(combination_group_member)
            .where(ended)
            .values(valid_to_known_at=func.now(), leave_event_id=event["id"])
        )
        assert _fails(
            session,
            update(combination_group_member).where(ended).values(valid_to_known_at=None),
        ) == (
            "P0001",
            "EREV-TRN-001: valid_to_known_at of erev.combination_group_member is already set",
        )

        proposed = combination_group_values(
            tenant_id, is_singleton=False, status="PROPOSED", criterion="25_9_A"
        )
        session.execute(insert(combination_group).values(**proposed))
        group = combination_group.c.id == proposed["id"]
        assert _fails(session, update(combination_group).where(group).values(status="APPLIED")) == (
            "P0001",
            "EREV-TRN-001: status of erev.combination_group cannot change from PROPOSED to APPLIED",
        )
        session.execute(update(combination_group).where(group).values(status="SUBMITTED"))
        session.execute(update(combination_group).where(group).values(dirty_since=func.now()))
        # A proposed group names its criterion.
        unnamed = combination_group_values(tenant_id, is_singleton=False, status="PROPOSED")
        sqlstate, message = _fails(session, insert(combination_group).values(**unnamed))
        assert (sqlstate, "ck_combination_group__criterion_required" in message) == (
            "23514",
            True,
        ), message


def _ledger_counts(session: Session) -> tuple[int, ...]:
    """Postings, lines and seals visible to ``session``."""
    return tuple(
        int(session.execute(select(func.count()).select_from(table)).scalar_one())
        for table in (subledger_posting, subledger_line, subledger_posting_seal)
    )


def _probe_lines(
    tenant_id: UUID, posting: dict[str, Any], parts: Any, *amounts: str, **extra: Any
) -> list[dict[str, Any]]:
    return [
        subledger_line_values(
            tenant_id, posting=posting, parts=parts, amount=Decimal(amount), **extra
        )
        for amount in amounts
    ]


def test_db_06_unbalanced_posting_rejected(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DB-06 (2) (CTR-3): the seal refuses a line count other than the posting's and an entry that
    # does not balance in transaction or functional currency (EREV-LED-001); balanced lines seal
    # with the trigger's control totals.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        parts = insert_ledger_parts(session, tenant_id)
        probe = session.begin_nested()
        posting = subledger_posting_values(tenant_id, parts=parts)
        session.execute(insert(subledger_posting).values(**posting))
        lines = _probe_lines(tenant_id, posting, parts, "10.00", "-9.00")
        session.execute(insert(subledger_line), lines)
        entity_id, period_id, posting_id = parts.chain.entity_id, parts.period_id, posting["id"]
        seal = ledger_seal_values(session, tenant_id, posting=posting, lines=lines)
        assert _fails(session, insert(subledger_posting_seal).values(**seal)) == (
            "P0001",
            f"EREV-LED-001: posting {posting_id} does not balance in transaction currency: "
            f"entity {entity_id} period {period_id} entry 1 USD sums 1.0000",
        )
        miscounted = {**seal, "line_count": 3}
        assert _fails(session, insert(subledger_posting_seal).values(**miscounted)) == (
            "P0001",
            f"EREV-LED-001: the seal of posting {posting_id} counts 3 lines, but the posting has 2",
        )
        third = _probe_lines(tenant_id, posting, parts, "-1.00", amount_functional=Decimal("-2.00"))
        session.execute(insert(subledger_line), third)
        seal = ledger_seal_values(session, tenant_id, posting=posting, lines=[*lines, *third])
        assert _fails(session, insert(subledger_posting_seal).values(**seal)) == (
            "P0001",
            f"EREV-LED-001: posting {posting_id} does not balance in functional currency: "
            f"entity {entity_id} period {period_id} entry 1 sums -1.0000",
        )
        probe.rollback()
        rows = insert_ledger_rows(session, tenant_id)
    with tenant_session(context, read_only=True) as session:
        stored = session.execute(
            select(
                subledger_posting_seal.c.chain_seq,
                subledger_posting_seal.c.line_count,
                subledger_posting_seal.c.control_totals,
            ).where(subledger_posting_seal.c.subledger_posting_id == rows.posting_id)
        ).one()
        assert _ledger_counts(session) == (1, 2, 1)
    assert tuple(stored) == (
        1,
        2,
        [
            {
                "entity_id": str(rows.parts.chain.entity_id),
                "period_id": str(rows.parts.period_id),
                "currency": "USD",
                "debit_txn": "10.0000",
                "credit_txn": "10.0000",
                "debit_functional": "10.0000",
                "credit_functional": "10.0000",
            }
        ],
    )


def test_db_06_unsealed_posting_rejected_at_commit(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-06 (1) and (3) (CTR-3): at commit a posting without its seal fails (EREV-LED-002); a line
    # joins only an unsealed posting of its book created in its transaction, with its period's end
    # date; a posting is sealed once.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with pytest.raises(exc.DBAPIError) as excinfo, tenant_session(context) as session:
        parts = insert_ledger_parts(session, tenant_id)
        unsealed = subledger_posting_values(tenant_id, parts=parts)
        session.execute(insert(subledger_posting).values(**unsealed))
        session.execute(
            insert(subledger_line), _probe_lines(tenant_id, unsealed, parts, "10.00", "-10.00")
        )
    assert _error(excinfo) == (
        "P0001",
        f"EREV-LED-002: subledger posting {unsealed['id']} of book ASC606 is not sealed",
    )
    with tenant_session(context, read_only=True) as session:
        assert _ledger_counts(session) == (0, 0, 0)

    with tenant_session(context) as session:
        rows = insert_ledger_rows(session, tenant_id)
    with tenant_session(context) as session:
        again = ledger_seal_values(session, tenant_id, posting=rows.posting, lines=rows.lines)
        assert _fails(session, insert(subledger_posting_seal).values(**again)) == (
            "P0001",
            f"EREV-LED-002: posting {rows.posting_id} is already sealed",
        )
        (late,) = _probe_lines(tenant_id, dict(rows.posting), rows.parts, "1.00")
        assert _fails(session, insert(subledger_line).values(**late)) == (
            "P0001",
            f"EREV-LED-002: posting {rows.posting_id} was created by another transaction, so line "
            f"{late['id']} cannot join it",
        )
        parts = insert_ledger_parts(session, tenant_id)
        posting = subledger_posting_values(tenant_id, parts=parts)
        session.execute(insert(subledger_posting).values(**posting))
        (other_book,) = _probe_lines(tenant_id, posting, parts, "1.00", book_code="IFRS15")
        assert _fails(session, insert(subledger_line).values(**other_book)) == (
            "P0001",
            f"EREV-LED-002: line {other_book['id']} of book IFRS15 joins posting "
            f"{posting['id']} of book ASC606",
        )
        (wrong_end,) = _probe_lines(
            tenant_id, posting, parts, "1.00", period_end_date=date(2026, 2, 28)
        )
        assert _fails(session, insert(subledger_line).values(**wrong_end)) == (
            "P0001",
            f"EREV-LED-002: line {wrong_end['id']} carries period_end_date 2026-02-28, not the end "
            f"date 2026-01-31 of period {parts.period_id}",
        )
        lines = _probe_lines(tenant_id, posting, parts, "10.00", "-10.00")
        session.execute(insert(subledger_line), lines)
        seal = ledger_seal_values(session, tenant_id, posting=posting, lines=lines)
        session.execute(insert(subledger_posting_seal).values(**seal))
        (extra,) = _probe_lines(tenant_id, posting, parts, "1.00")
        assert _fails(session, insert(subledger_line).values(**extra)) == (
            "P0001",
            f"EREV-LED-002: posting {posting['id']} is sealed, so line {extra['id']} cannot "
            "join it",
        )
    with tenant_session(context, read_only=True) as session:
        assert _ledger_counts(session) == (2, 4, 2)


def test_db_06_quantization_enforced(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DB-06 (1) (CTR-3): amounts are quantized to the currency minor unit (EREV-LED-004).
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        parts = insert_ledger_parts(session, tenant_id)
        posting = subledger_posting_values(tenant_id, parts=parts)
        session.execute(insert(subledger_posting).values(**posting))
        (cents,) = _probe_lines(tenant_id, posting, parts, "10.005")
        assert _fails(session, insert(subledger_line).values(**cents)) == (
            "P0001",
            f"EREV-LED-004: line {cents['id']} amounts 10.0050 USD and 10.0050 USD are not "
            "quantized to the currency minor units",
        )
        (yen,) = _probe_lines(
            tenant_id, posting, parts, "1200.50", txn_currency="JPY", functional_currency="JPY"
        )
        assert _fails(session, insert(subledger_line).values(**yen)) == (
            "P0001",
            f"EREV-LED-004: line {yen['id']} amounts 1200.5000 JPY and 1200.5000 JPY are not "
            "quantized to the currency minor units",
        )
        lines = _probe_lines(tenant_id, posting, parts, "10.01", "-10.01")
        session.execute(insert(subledger_line), lines)
        seal = ledger_seal_values(session, tenant_id, posting=posting, lines=lines)
        session.execute(insert(subledger_posting_seal).values(**seal))
    with tenant_session(context, read_only=True) as session:
        assert _ledger_counts(session) == (1, 2, 1)


def test_db_06_chain_mismatch_rejected(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DB-06 (2) (CTR-3): a seal names the book's last seal (EREV-LED-005); the trigger assigns
    # chain_seq from ledger_chain_head and advances the head.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        parts = insert_ledger_parts(session, tenant_id)
        posting = subledger_posting_values(tenant_id, parts=parts)
        session.execute(insert(subledger_posting).values(**posting))
        lines = _probe_lines(tenant_id, posting, parts, "10.00", "-10.00")
        session.execute(insert(subledger_line), lines)
        wrong = ledger_seal_values(
            session, tenant_id, posting=posting, lines=lines, previous="0" * 64
        )
        assert _fails(session, insert(subledger_posting_seal).values(**wrong)) == (
            "P0001",
            f"EREV-LED-005: the seal of posting {posting['id']} names previous seal "
            f"{'0' * 64}, but the ASC606 chain head is none",
        )
        first = ledger_seal_values(session, tenant_id, posting=posting, lines=lines)
        session.execute(insert(subledger_posting_seal).values(**first))
    with tenant_session(context) as session:
        parts = insert_ledger_parts(session, tenant_id)
        second_posting = subledger_posting_values(tenant_id, parts=parts)
        session.execute(insert(subledger_posting).values(**second_posting))
        lines = _probe_lines(tenant_id, second_posting, parts, "25.00", "-25.00")
        session.execute(insert(subledger_line), lines)
        stale = ledger_seal_values(
            session, tenant_id, posting=second_posting, lines=lines, previous=None
        )
        assert _fails(session, insert(subledger_posting_seal).values(**stale)) == (
            "P0001",
            f"EREV-LED-005: the seal of posting {second_posting['id']} names previous seal none, "
            f"but the ASC606 chain head is {first['seal_sha256']}",
        )
        second = ledger_seal_values(session, tenant_id, posting=second_posting, lines=lines)
        session.execute(insert(subledger_posting_seal).values(**second))
    with tenant_session(context, read_only=True) as session:
        seals = session.execute(
            select(
                subledger_posting_seal.c.chain_seq,
                subledger_posting_seal.c.prev_seal_sha256,
                subledger_posting_seal.c.seal_sha256,
            ).order_by(subledger_posting_seal.c.chain_seq)
        ).all()
        head = session.execute(
            select(
                ledger_chain_head_table.c.book_code,
                ledger_chain_head_table.c.last_chain_seq,
                ledger_chain_head_table.c.last_seal_sha256,
            ).order_by(ledger_chain_head_table.c.book_code)
        ).all()
    assert [tuple(row) for row in seals] == [
        (1, None, first["seal_sha256"]),
        (2, first["seal_sha256"], second["seal_sha256"]),
    ]
    assert [tuple(row) for row in head] == [
        ("ASC606", 2, second["seal_sha256"]),
        ("IFRS15", 0, None),
        ("LEGACY", 0, None),
    ]


def test_db_07_posting_into_future_period_rejected(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-07 (CTR-3): a line posts only into an open, closing or reopened period of its entity and
    # book (EREV-LED-003); a reopened period marks the line post-reopen; an origin period ends
    # before the posting period starts.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        parts = insert_ledger_parts(session, tenant_id, state="future")
        probe = session.begin_nested()
        posting = subledger_posting_values(tenant_id, parts=parts)
        session.execute(insert(subledger_posting).values(**posting))
        (future,) = _probe_lines(tenant_id, posting, parts, "10.00")
        assert _fails(session, insert(subledger_line).values(**future)) == (
            "P0001",
            f"EREV-LED-003: period {parts.period_id} of entity {parts.chain.entity_id} is future "
            f"in book ASC606, so line {future['id']} cannot post into it",
        )
        probe.rollback()

    with tenant_session(context) as session:
        parts = insert_ledger_parts(session, tenant_id, state="reopened")
        # a reopened period is under its REOPEN record, which DB-07 reads for the flag (04 rev
        # 1.184; revision 0113): the fixture writes it as the reopen decision does
        insert_reopen_record(
            session, tenant_id, entity_id=parts.chain.entity_id, period_id=parts.period_id
        )
        calendar_id = session.execute(
            select(legal_entity.c.calendar_id).where(legal_entity.c.id == parts.chain.entity_id)
        ).scalar_one()
        february = period_values(
            tenant_id,
            calendar_id=calendar_id,
            period_no=2,
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 28),
        )
        session.execute(insert(period).values(**february))
        session.execute(
            insert(period_state).values(
                **period_state_values(
                    tenant_id,
                    entity_id=parts.chain.entity_id,
                    period_id=february["id"],
                    period_end_date=date(2026, 2, 28),
                    state="open",
                )
            )
        )
        posting = subledger_posting_values(tenant_id, parts=parts)
        session.execute(insert(subledger_posting).values(**posting))
        (backwards,) = _probe_lines(
            tenant_id,
            posting,
            parts,
            "5.00",
            origin_period_id=february["id"],
            reason_code="LATE_EVENT",
        )
        assert _fails(session, insert(subledger_line).values(**backwards)) == (
            "P0001",
            f"EREV-LED-003: origin period {february['id']} of line {backwards['id']} does not end "
            f"before period {parts.period_id} starts",
        )
        reopened = _probe_lines(tenant_id, posting, parts, "10.00", "-10.00")
        late = _probe_lines(
            tenant_id,
            posting,
            parts,
            "5.00",
            "-5.00",
            entry_no=2,
            period_id=february["id"],
            period_end_date=date(2026, 2, 28),
            origin_period_id=parts.period_id,
            reason_code="LATE_EVENT",
        )
        session.execute(insert(subledger_line), [*reopened, *late])
        seal = ledger_seal_values(session, tenant_id, posting=posting, lines=[*reopened, *late])
        session.execute(insert(subledger_posting_seal).values(**seal))
    with tenant_session(context, read_only=True) as session:
        stored = session.execute(
            select(
                subledger_line.c.entry_no,
                subledger_line.c.amount_txn,
                subledger_line.c.is_post_reopen,
                subledger_line.c.origin_period_id,
            )
            .where(subledger_line.c.subledger_posting_id == posting["id"])
            .order_by(subledger_line.c.entry_no, subledger_line.c.amount_txn)
        ).all()
    assert [tuple(row) for row in stored] == [
        (1, Decimal("-10.0000"), True, None),
        (1, Decimal("10.0000"), True, None),
        (2, Decimal("-5.0000"), False, parts.period_id),
        (2, Decimal("5.0000"), False, parts.period_id),
    ]


def test_db_05_functional_currency_frozen_after_posting(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-05 (CTR-3; BS3-D-07): functional currency and time zone of an entity change freely until a
    # subledger line of the entity exists, then fail (EREV-REF-001); other columns still change,
    # and the period of the line is frozen.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        parts = insert_ledger_parts(session, tenant_id)
        entity_row = legal_entity.c.id == parts.chain.entity_id
        changed = session.execute(
            update(legal_entity)
            .where(entity_row)
            .values(code="AVM-DE", functional_currency="EUR", time_zone="Europe/Berlin")
        )
        assert cast(CursorResult[Any], changed).rowcount == 1
        posting = subledger_posting_values(tenant_id, parts=parts)
        session.execute(insert(subledger_posting).values(**posting))
        lines = _probe_lines(
            tenant_id,
            posting,
            parts,
            "10.00",
            "-10.00",
            txn_currency="EUR",
            functional_currency="EUR",
        )
        session.execute(insert(subledger_line), lines)
        seal = ledger_seal_values(session, tenant_id, posting=posting, lines=lines)
        session.execute(insert(subledger_posting_seal).values(**seal))
    with tenant_session(context) as session:
        frozen = (
            "EREV-REF-001: functional_currency and time_zone of entity AVM-DE of erev.legal_entity "
            "are frozen: a subledger line of the entity exists"
        )
        for values in ({"functional_currency": "USD"}, {"time_zone": "America/New_York"}):
            assert _fails(session, update(legal_entity).where(entity_row).values(**values)) == (
                "P0001",
                frozen,
            )
        renamed = session.execute(
            update(legal_entity).where(entity_row).values(name="Avenmoor Sensorik GmbH (Demo)")
        )
        assert cast(CursorResult[Any], renamed).rowcount == 1
        sqlstate, message = _fails(
            session, update(period).where(period.c.id == parts.period_id).values(name="Renamed")
        )
        assert (sqlstate, message.startswith("EREV-REF-001: period FY2026-P01 of erev.period")) == (
            "P0001",
            True,
        )


@pytest.mark.control("CTL-022")
def test_ctl_022_unbalanced_entry_refused_by_database(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # CTL-022 (REQ-JE-001; D-16): the seal of a posting with an entry whose Σ amount_txn ≠ 0 fails,
    # and nothing of the posting commits; the chain head stays at 0.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with pytest.raises(exc.DBAPIError) as excinfo, tenant_session(context) as session:
        parts = insert_ledger_parts(session, tenant_id)
        posting = subledger_posting_values(tenant_id, parts=parts)
        session.execute(insert(subledger_posting).values(**posting))
        lines = [
            *_probe_lines(tenant_id, posting, parts, "10.00", "-10.00"),
            *_probe_lines(tenant_id, posting, parts, "5.00", "-4.00", entry_no=2),
        ]
        session.execute(insert(subledger_line), lines)
        seal = ledger_seal_values(session, tenant_id, posting=posting, lines=lines)
        session.execute(insert(subledger_posting_seal).values(**seal))
    assert _error(excinfo) == (
        "P0001",
        f"EREV-LED-001: posting {posting['id']} does not balance in transaction currency: entity "
        f"{parts.chain.entity_id} period {parts.period_id} entry 2 USD sums 1.0000",
    )
    with tenant_session(context, read_only=True) as session:
        assert _ledger_counts(session) == (0, 0, 0)
        head = session.execute(
            select(
                ledger_chain_head_table.c.last_chain_seq, ledger_chain_head_table.c.last_seal_sha256
            ).where(ledger_chain_head_table.c.book_code == "ASC606")
        ).one()
    assert tuple(head) == (0, None)


def _allocated_version(
    session: Session, tenant_id: UUID, *, transaction_price: Decimal, amounts: tuple[Decimal, ...]
) -> VersionRows:
    """Version 1 at ``transaction_price`` with one obligation version per amount."""
    rows = insert_version_rows(session, tenant_id, transaction_price=transaction_price)
    for index, amount in enumerate(amounts, start=1):
        parts = insert_obligation_rows(session, tenant_id, rows, obligation_key=f"O{index}")
        session.execute(
            insert(obligation_version).values(
                **obligation_version_values(
                    tenant_id,
                    contract_version_id=rows.version_id,
                    contract_id=rows.chain.contract_id,
                    combination_group_id=rows.chain.group_id,
                    entity_id=rows.chain.entity_id,
                    allocated_amount=amount,
                    obligation_key=f"O{index}",
                    **parts,
                )
            )
        )
    return rows


def test_db_17_allocation_identity_enforced(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DB-17 (CTR-2): at commit, the obligation versions of a contract version allocate
    # transaction_price − consideration_payable_amount (EREV-ALC-001, rev 1.2 V1); an obligation
    # version whose allocation departs from revenue_cum + scheduled + awaiting fails its check.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with pytest.raises(exc.DBAPIError) as excinfo, tenant_session(context) as session:
        refused = _allocated_version(
            session, tenant_id, transaction_price=Decimal("100"), amounts=(Decimal("90"),)
        )
    sqlstate, message = _error(excinfo)
    assert sqlstate == "P0001"
    assert message == (
        f"EREV-ALC-001: obligation versions of contract version {refused.version_id} allocate "
        "90.0000, not transaction_price 100.0000 less consideration_payable_amount 0.0000"
    )
    with tenant_session(context, read_only=True) as session:
        stored = select(func.count()).select_from(contract_version)
        assert session.execute(stored).scalar_one() == 0
    # Allocations that add up commit: two obligations of 60 and 40, and a version whose
    # consideration payable of −10 is added back to its price of 100 (S04-R-02).
    with tenant_session(context) as session:
        kept = _allocated_version(
            session,
            tenant_id,
            transaction_price=Decimal("100"),
            amounts=(Decimal("60"), Decimal("40")),
        )
    with tenant_session(context) as session:
        payable = insert_version_rows(
            session,
            tenant_id,
            transaction_price=Decimal("100"),
            consideration_payable_amount=Decimal("-10"),
        )
        parts = insert_obligation_rows(session, tenant_id, payable)
        session.execute(
            insert(obligation_version).values(
                **obligation_version_values(
                    tenant_id,
                    contract_version_id=payable.version_id,
                    contract_id=payable.chain.contract_id,
                    combination_group_id=payable.chain.group_id,
                    entity_id=payable.chain.entity_id,
                    allocated_amount=Decimal("110"),
                    **parts,
                )
            )
        )
    with tenant_session(context, read_only=True) as session:
        totals = session.execute(
            select(
                obligation_version.c.contract_version_id,
                func.sum(obligation_version.c.allocated_amount),
            ).group_by(obligation_version.c.contract_version_id)
        ).all()
    assert sorted((str(version_id), total) for version_id, total in totals) == sorted(
        [(str(kept.version_id), Decimal("100")), (str(payable.version_id), Decimal("110"))]
    )
    # The obligation identity is a check: 100 allocated with 90 awaiting its trigger.
    with tenant_session(context) as session:
        rows = insert_version_rows(session, tenant_id, transaction_price=Decimal("100"))
        parts = insert_obligation_rows(session, tenant_id, rows)
        unbalanced = obligation_version_values(
            tenant_id,
            contract_version_id=rows.version_id,
            contract_id=rows.chain.contract_id,
            combination_group_id=rows.chain.group_id,
            entity_id=rows.chain.entity_id,
            awaiting_trigger_amount=Decimal("90"),
            **parts,
        )
        sqlstate, message = _fails(session, insert(obligation_version).values(**unbalanced))
        assert (sqlstate, "ck_obligation_version__allocation" in message) == ("23514", True)
        session.execute(
            insert(obligation_version).values(
                **{**unbalanced, "awaiting_trigger_amount": Decimal("100")}
            )
        )


def test_db_10_judgement_reviewer_differs_from_preparer(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-10 (CTR-7): tg_judgement_record__review refuses a reviewer equal to the preparer
    # (EREV-APR-001) on INSERT and UPDATE; another reviewer passes and is then set once (DB-03).
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    preparer, reviewer = new_id(), new_id()
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        record = judgement_record_values(
            tenant_id, created_by=preparer, created_by_kind="USER", status="SUBMITTED"
        )
        session.execute(insert(judgement_record).values(**record))
        target = judgement_record.c.id == record["id"]
        assert _fails(
            session,
            update(judgement_record)
            .where(target)
            .values(status="REVIEWED", reviewer_id=preparer, reviewed_at=func.now()),
        ) == (
            "P0001",
            f"EREV-APR-001: the preparer of judgement record {record['id']} cannot review it",
        )
        own = judgement_record_values(
            tenant_id, created_by=preparer, created_by_kind="USER", reviewer_id=preparer
        )
        sqlstate, message = _fails(session, insert(judgement_record).values(**own))
        assert (sqlstate, message.split(":", 1)[0]) == ("P0001", "EREV-APR-001"), message
        session.execute(
            update(judgement_record)
            .where(target)
            .values(status="REVIEWED", reviewer_id=reviewer, reviewed_at=func.now())
        )
        assert _fails(
            session, update(judgement_record).where(target).values(reviewer_id=new_id())
        ) == (
            "P0001",
            "EREV-TRN-001: reviewer_id of erev.judgement_record is already set",
        )
        assert _fails(session, update(judgement_record).where(target).values(status="DRAFT")) == (
            "P0001",
            "EREV-TRN-001: status of erev.judgement_record cannot change from REVIEWED to DRAFT",
        )


def test_db_03_policy_override_transitions(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DB-03 (CTR-15): policy_override is editable while DRAFT, then changes status along E-12 with
    # approval_request_id, approved_at (once) and SC-M only; one APPROVED override per contract,
    # obligation and key (ux_policy_override__active); the level names its subject (T-CON-23).
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        chain = insert_contract_rows(session, tenant_id, head_stream_version=1)
        override = policy_override_values(tenant_id, contract_id=chain.contract_id)
        session.execute(insert(policy_override).values(**override))
        target = policy_override.c.id == override["id"]
        session.execute(
            update(policy_override)
            .where(target)
            .values(value="ACTUAL_RETURNS_ONLY", rationale="Returns are immaterial.")
        )
        session.execute(update(policy_override).where(target).values(status="SUBMITTED"))
        assert _fails(session, update(policy_override).where(target).values(rationale="Later")) == (
            "P0001",
            "EREV-TRN-001: columns rationale of erev.policy_override cannot change",
        )
        superseded = update(policy_override).where(target).values(status="SUPERSEDED")
        assert _fails(session, superseded) == (
            "P0001",
            "EREV-TRN-001: status of erev.policy_override cannot change "
            "from SUBMITTED to SUPERSEDED",
        )
        # The contract of an override is not granted for UPDATE at all.
        moved = update(policy_override).where(target).values(contract_id=new_id())
        assert _fails(session, moved)[0] == "42501"
        approved_at = datetime(2026, 9, 12, 12, tzinfo=UTC)
        session.execute(
            update(policy_override).where(target).values(status="APPROVED", approved_at=approved_at)
        )
        later = update(policy_override).where(target).values(approved_at=approved_at + timedelta(1))
        assert _fails(session, later) == (
            "P0001",
            "EREV-TRN-001: approved_at of erev.policy_override is already set",
        )
        twin = policy_override_values(
            tenant_id, contract_id=chain.contract_id, status="APPROVED", approved_at=approved_at
        )
        assert _fails(session, insert(policy_override).values(**twin))[0] == "23505"
        unnamed = policy_override_values(
            tenant_id, contract_id=chain.contract_id, level="OBLIGATION"
        )
        assert _fails(session, insert(policy_override).values(**unnamed))[0] == "23514"


APPROVED_AT = datetime(2026, 2, 3, 9, tzinfo=UTC)


def _move_batch(rows: JournalRows, state: str, **values: Any) -> Executable:
    """The UPDATE that moves the probe batch of ``rows`` to ``state`` with ``values``."""
    target = journal_batch.c.id == rows.batch["id"]
    return update(journal_batch).where(target).values(state=state, **values)


def test_db_16_journal_run_coverage_contiguous(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-16 (CLO-1; 04 rev 1.106, revision 0085 — supervisor ruling R-32 on security finding SC-7):
    # the non-cancelled runs of one (entity, book, period) cover contiguous, non-overlapping seal
    # ranges from 0 WHATEVER THEIR MODE (EREV-JR-001); a cancelled run's range is covered again. A
    # DELTA run outputs the primary lines a GROSS run outputs, so it starts where the key's runs
    # end — never again at 0 beside a GROSS run — and its LEGACY range is held to the same rule.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        parts = insert_journal_parts(session, tenant_id)
        key = f"entity {parts.entity_id}, book ASC606 and period {parts.period_id}"
        for from_seq, to_seq, covered in ((3, 5, 0), (5, 9, 4), (3, 9, 4), (0, 9, 4)):
            if covered == 4 and from_seq == 5:
                first = journal_run_values(tenant_id, parts=parts, to_chain_seq=4)
                session.execute(insert(journal_run).values(**first))
            run = journal_run_values(
                tenant_id, parts=parts, from_chain_seq=from_seq, to_chain_seq=to_seq
            )
            assert _fails(session, insert(journal_run).values(**run)) == (
                "P0001",
                f"EREV-JR-001: run {run['run_no']} starts at chain sequence {from_seq}, but the "
                f"runs of {key} cover up to {covered}",
            )
        second = journal_run_values(tenant_id, parts=parts, from_chain_seq=4, to_chain_seq=9)
        session.execute(insert(journal_run).values(**second))
        session.execute(
            update(journal_run)
            .where(journal_run.c.id == second["id"])
            .values(state="cancelled", cancelled_at=APPROVED_AT)
        )
        again = journal_run_values(tenant_id, parts=parts, from_chain_seq=4, to_chain_seq=7)
        session.execute(insert(journal_run).values(**again))

        def delta(**ranges: int) -> dict[str, Any]:
            return journal_run_values(
                tenant_id, parts=parts, mode="DELTA", delta_book_code="LEGACY", **ranges
            )

        # SC-7: the GROSS runs cover (0, 7]; a DELTA run over the same seals is refused — the run
        # this test accepted until revision 0085 ("another mode starts at 0").
        replay = delta(to_chain_seq=2)
        assert _fails(session, insert(journal_run).values(**replay)) == (
            "P0001",
            f"EREV-JR-001: run {replay['run_no']} starts at chain sequence 0, but the runs of "
            f"{key} cover up to 7",
        )
        # The legitimate DELTA run continues the key's coverage and opens the LEGACY range at 0.
        continued = delta(
            from_chain_seq=7, to_chain_seq=9, delta_from_chain_seq=0, delta_to_chain_seq=3
        )
        session.execute(insert(journal_run).values(**continued))
        # The LEGACY range of a later DELTA run starts where the key's LEGACY ranges end.
        legacy_replay = delta(
            from_chain_seq=9, to_chain_seq=9, delta_from_chain_seq=0, delta_to_chain_seq=5
        )
        assert _fails(session, insert(journal_run).values(**legacy_replay)) == (
            "P0001",
            f"EREV-JR-001: run {legacy_replay['run_no']} starts its LEGACY range at chain "
            f"sequence 0, but the runs of {key} cover the LEGACY book up to 3",
        )
        legacy_continued = delta(
            from_chain_seq=9, to_chain_seq=9, delta_from_chain_seq=3, delta_to_chain_seq=5
        )
        session.execute(insert(journal_run).values(**legacy_continued))
        # ... and a GROSS run after the DELTA runs continues from the same maximum.
        gross_replay = journal_run_values(tenant_id, parts=parts, from_chain_seq=7, to_chain_seq=11)
        assert _fails(session, insert(journal_run).values(**gross_replay)) == (
            "P0001",
            f"EREV-JR-001: run {gross_replay['run_no']} starts at chain sequence 7, but the runs "
            f"of {key} cover up to 9",
        )
        later = journal_run_values(tenant_id, parts=parts, from_chain_seq=9, to_chain_seq=11)
        session.execute(insert(journal_run).values(**later))
    with tenant_session(context, read_only=True) as session:
        ranges = session.execute(
            select(
                journal_run.c.mode,
                journal_run.c.state,
                journal_run.c.from_chain_seq,
                journal_run.c.to_chain_seq,
                journal_run.c.delta_from_chain_seq,
                journal_run.c.delta_to_chain_seq,
            )
        ).all()
    assert {tuple(row) for row in ranges} == {
        ("GROSS", "draft", 0, 4, None, None),
        ("GROSS", "cancelled", 4, 9, None, None),
        ("GROSS", "draft", 4, 7, None, None),
        ("DELTA", "draft", 7, 9, 0, 3),
        ("DELTA", "draft", 9, 9, 3, 5),
        ("GROSS", "draft", 9, 11, None, None),
    }


@pytest.mark.control("CTL-022")
def test_ctl_022_batch_approve_rejects_unbalanced(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # CTL-022 (REQ-JE-001; DB-16): a batch with lines Dr 295.69 / Cr 295.68 cannot move to approved
    # (EREV-JE-001); with Dr 295.69 / Cr 295.69 (POLICIES CHK-022, Contract 1) it can. A line added
    # after the approval rolls the transaction back. Since revision 0104 (04 DB-16 rev 1.205;
    # supervisor ruling R-112 (b) (6)) it is refused at its insert — the batch is no longer draft,
    # EREV-JE-003 — and never reaches the deferred constraint trigger, which checked the lines
    # again at commit and answered "counts 2 lines, but has 3" (STALE EXPECTATION under that
    # ruling). The deferred check stands behind the guard: ``test_journal_guards.py`` holds it
    # with the guard disabled.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        unbalanced = insert_journal_rows(
            session,
            tenant_id,
            lines=((Decimal("295.69"), Decimal("0")), (Decimal("0"), Decimal("295.68"))),
        )
        assert _fails(session, _move_batch(unbalanced, "approved")) == (
            "P0001",
            f"EREV-JE-001: batch {unbalanced.batch['external_id']} does not balance: debits "
            "295.6900 and credits 295.6800 USD, debits 295.6900 and credits 295.6800 USD",
        )
        balanced = insert_journal_rows(session, tenant_id)
        session.execute(_move_batch(balanced, "approved"))
    with tenant_session(context, read_only=True) as session:
        states = {
            row_id: str(state)
            for row_id, state in session.execute(select(journal_batch.c.id, journal_batch.c.state))
        }
    assert states == {unbalanced.batch["id"]: "draft", balanced.batch["id"]: "approved"}

    with pytest.raises(exc.DBAPIError) as excinfo, tenant_session(context) as session:
        late = insert_journal_rows(session, tenant_id)
        session.execute(_move_batch(late, "approved"))
        extra = journal_line_values(
            tenant_id,
            parts=late.parts,
            entry_id=late.entries[0]["id"],
            batch_id=late.batch["id"],
            line_no=3,
            debit=Decimal("1.00"),
        )
        session.execute(insert(journal_line).values(**extra))
    assert _error(excinfo) == (
        "P0001",
        f"EREV-JE-003: journal batch {late.batch['id']} is approved, so journal line "
        f"{extra['id']} cannot join it: a batch takes lines only while it is draft",
    )
    with tenant_session(context, read_only=True) as session:
        assert session.execute(select(func.count()).select_from(journal_batch)).scalar_one() == 2


def test_db_16_je_sequence_gap(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DB-16 (CLO-1): on approval the je_seq values of a run per entity form a contiguous range after
    # the entity's greatest earlier number (EREV-JE-002): entries 1, 2 and 4 fail; 1, 2 and 3 pass;
    # a later run from 5 fails while one from 4 passes.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")

    def approve(rows: JournalRows) -> Executable:
        target = journal_run.c.id == rows.run["id"]
        return update(journal_run).where(target).values(state="approved", approved_at=APPROVED_AT)

    with tenant_session(context) as session:
        gapped = insert_journal_rows(session, tenant_id, je_seqs=(1, 2, 4))
        assert _fails(session, approve(gapped)) == (
            "P0001",
            f"EREV-JE-002: journal entries of run {gapped.run['run_no']} have a sequence gap: "
            f"entity {gapped.parts.entity_id} numbers je_seq 1 to 4 in 3 entries after je_seq 0",
        )
    with tenant_session(context) as session:
        parts = insert_journal_parts(session, tenant_id)
        first = insert_journal_rows(session, tenant_id, parts=parts, je_seqs=(1, 2, 3))
        session.execute(approve(first))
        skipped = insert_journal_rows(session, tenant_id, parts=parts, je_seqs=(5, 6))
        assert _fails(session, approve(skipped)) == (
            "P0001",
            f"EREV-JE-002: journal entries of run {skipped.run['run_no']} have a sequence gap: "
            f"entity {parts.entity_id} numbers je_seq 5 to 6 in 2 entries after je_seq 3",
        )
        following = insert_journal_rows(session, tenant_id, parts=parts, je_seqs=(4,))
        session.execute(approve(following))
    with tenant_session(context, read_only=True) as session:
        states = {
            row_id: str(state)
            for row_id, state in session.execute(select(journal_run.c.id, journal_run.c.state))
        }
    assert states == {
        gapped.run["id"]: "draft",
        first.run["id"]: "approved",
        skipped.run["id"]: "draft",
        following.run["id"]: "approved",
    }


def test_db_15_journal_batch_sandbox_csv_only(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DB-15 (CLO-1; REQ-PLT-022): in a sandbox tenant a batch reaches exported only for the CSV
    # adapter and without an outbox message (EREV-SBX-001); a production tenant exports through
    # NETSUITE.
    sandbox = insert_sandbox_tenant(keyring)
    context = DbContext(tenant_id=sandbox, user_id=None, entity_scope="*")
    exported = {"exported_at": APPROVED_AT, "attempt_count": 1}
    with tenant_session(context) as session:
        parts = insert_journal_parts(session, sandbox)
        netsuite = insert_journal_rows(session, sandbox, parts=parts, adapter="NETSUITE")
        csv = insert_journal_rows(session, sandbox, parts=parts, je_seqs=(2,))
        for rows in (netsuite, csv):
            session.execute(_move_batch(rows, "approved"))
        assert _fails(session, _move_batch(netsuite, "exported", **exported)) == (
            "P0001",
            f"EREV-SBX-001: batch {netsuite.batch['external_id']} of a sandbox tenant is exported "
            "only as a CSV download, not through adapter NETSUITE or an outbox message",
        )
        with_message = _move_batch(csv, "exported", outbox_message_id=new_id(), **exported)
        assert _fails(session, with_message) == (
            "P0001",
            f"EREV-SBX-001: batch {csv.batch['external_id']} of a sandbox tenant is exported only "
            "as a CSV download, not through adapter CSV or an outbox message",
        )
        session.execute(_move_batch(csv, "exported", **exported))
    with tenant_session(context, read_only=True) as session:
        states = {
            str(adapter): str(state)
            for adapter, state in session.execute(
                select(journal_batch.c.adapter, journal_batch.c.state)
            )
        }
        messages = session.execute(select(func.count()).select_from(outbox_message)).scalar_one()
    assert (states, messages) == ({"NETSUITE": "approved", "CSV": "exported"}, 0)

    production = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=production, user_id=None, entity_scope="*")) as session:
        rows = insert_journal_rows(session, production, adapter="NETSUITE")
        session.execute(_move_batch(rows, "approved"))
        session.execute(_move_batch(rows, "exported", **exported))


@pytest.mark.control("CTL-015")
def test_ctl_015_journal_line_closed_period_guard(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # CTL-015 (REQ-CLS-002; BS4-D-02): a journal line posts only into an open, closing or reopened
    # period of its entity and book (EREV-LED-003), as a subledger line does (DB-07).
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    months = (
        ("closed", date(2026, 2, 1), date(2026, 2, 28)),
        ("permanently_locked", date(2026, 3, 1), date(2026, 3, 31)),
        ("open", date(2026, 4, 1), date(2026, 4, 30)),
        ("closing", date(2026, 5, 1), date(2026, 5, 31)),
        ("reopened", date(2026, 6, 1), date(2026, 6, 30)),
        (None, date(2026, 7, 1), date(2026, 7, 31)),
    )
    posted: set[UUID] = set()
    with tenant_session(context) as session:
        rows = insert_journal_rows(session, tenant_id, lines=())
        parts = rows.parts
        for number, (state, start, end) in enumerate(months, start=2):
            month = period_values(
                tenant_id,
                calendar_id=parts.calendar_id,
                period_no=number,
                start_date=start,
                end_date=end,
            )
            session.execute(insert(period).values(**month))
            if state is not None:
                month_state = period_state_values(
                    tenant_id,
                    entity_id=parts.entity_id,
                    period_id=month["id"],
                    period_end_date=end,
                    state=state,
                )
                session.execute(insert(period_state).values(**month_state))
            line = journal_line_values(
                tenant_id,
                parts=parts,
                entry_id=rows.entries[0]["id"],
                batch_id=rows.batch["id"],
                line_no=number,
                period_id=month["id"],
            )
            if state in ("open", "closing", "reopened"):
                session.execute(insert(journal_line).values(**line))
                posted.add(line["id"])
                continue
            assert _fails(session, insert(journal_line).values(**line)) == (
                "P0001",
                f"EREV-LED-003: period {month['id']} of entity {parts.entity_id} is "
                f"{state or 'without a state'} in book ASC606, so journal line {line['id']} cannot "
                "post into it",
            )
    with tenant_session(context, read_only=True) as session:
        stored = set(session.scalars(select(journal_line.c.id)))
    assert (len(posted), stored) == (3, posted)


@pytest.mark.control("CTL-015")
def test_ctl_015_subledger_insert_into_closed_period(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # CTL-015 (REQ-CLS-002; BUILD_SPEC CLO-3): as erev_app, a subledger line for a closed or
    # permanently locked period raises EREV-LED-003 (DB-07); an open, closing or reopened period
    # accepts it.
    # The stored flag (04 T-SL-04 and DB-07 rev 1.184, revision 0113; supervisor ruling R-117 (c)):
    # a line is a post-reopen line while its period's current lock record is a REOPEN — "locked
    # once and not locked now" — whatever the state literal reads. The guard stored `state =
    # 'reopened'` until then, so the two cases under a REOPEN record that read `closing` (the soft
    # close that follows a reopen) and `open` (a history written before rev 1.170, or its replay)
    # were stored false. The Python reading of the same fact (`periods.under_reopen`) and the
    # approval rule built on it (`periods.auto_approval_barred`: PRD BR-CLS-04, BR-CLS-06) are
    # held to the guard on every case.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    cases = (
        ("closed", "closed", False),
        ("permanently_locked", "permanently_locked", False),
        ("open", "open", False),
        ("closing", "closing", False),
        ("reopened", "reopened", True),
        ("closing under REOPEN", "closing", True),
        ("open under REOPEN", "open", True),
    )
    outcomes: dict[str, str] = {}
    readings: dict[str, tuple[bool, bool]] = {}
    with tenant_session(context) as session:
        for label, state, reopened in cases:
            parts = insert_ledger_parts(session, tenant_id, state=state)
            scope = {
                "entity_id": parts.chain.entity_id,
                "book_code": BookCode.ASC606,
                "period_id": parts.period_id,
            }
            if reopened:
                insert_reopen_record(
                    session, tenant_id, entity_id=parts.chain.entity_id, period_id=parts.period_id
                )
            readings[label] = (
                periods.under_reopen(session, **scope),
                periods.auto_approval_barred(session, **scope),
            )
            probe = session.begin_nested()
            posting = subledger_posting_values(tenant_id, parts=parts)
            session.execute(insert(subledger_posting).values(**posting))
            line = subledger_line_values(tenant_id, posting=posting, parts=parts)
            if state in ("closed", "permanently_locked"):
                assert _fails(session, insert(subledger_line).values(**line)) == (
                    "P0001",
                    f"EREV-LED-003: period {parts.period_id} of entity {parts.chain.entity_id} is "
                    f"{state} in book ASC606, so line {line['id']} cannot post into it",
                )
                outcomes[label] = "refused"
            else:
                session.execute(insert(subledger_line).values(**line))
                stored = session.execute(
                    select(subledger_line.c.is_post_reopen).where(subledger_line.c.id == line["id"])
                ).scalar_one()
                outcomes[label] = f"accepted is_post_reopen={stored}"
            probe.rollback()
    assert outcomes == {
        "closed": "refused",
        "permanently_locked": "refused",
        "open": "accepted is_post_reopen=False",
        "closing": "accepted is_post_reopen=False",
        "reopened": "accepted is_post_reopen=True",
        "closing under REOPEN": "accepted is_post_reopen=True",
        "open under REOPEN": "accepted is_post_reopen=True",
    }
    # (under reopen, no auto-approval rule applies): the flag of an accepted line equals the
    # first member, and a soft close bars the rules on its own (BR-CLS-04)
    assert readings == {
        "closed": (False, False),
        "permanently_locked": (False, False),
        "open": (False, False),
        "closing": (False, True),
        "reopened": (True, True),
        "closing under REOPEN": (True, True),
        "open under REOPEN": (True, True),
    }


def test_db_03_manual_adjustment_withdraw_revise_and_discard_pairs(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-03 (CLO-12; revision 0093; PRD SM-10 rev 1.49; supervisor ruling R-51 (b)): the pairs of
    # T-CON-06 — SUBMITTED → DRAFT (the request withdrawn or voided as stale), REJECTED → DRAFT
    # (revise and resubmit), DRAFT → VOIDED (discard) — and nothing beyond them: a REJECTED
    # adjustment is neither edited nor resubmitted as it stands, a SUBMITTED one is not discarded,
    # and an APPROVED, POSTED or VOIDED one never returns to DRAFT.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        ledger = insert_ledger_parts(session, tenant_id)

        def fresh(*statuses: str) -> Callable[..., Executable]:
            """A new DRAFT adjustment moved along ``statuses``; returns its UPDATE builder."""
            adjustment = manual_adjustment_values(
                tenant_id,
                contract_id=ledger.chain.contract_id,
                entity_id=ledger.chain.entity_id,
                period_id=ledger.period_id,
            )
            session.execute(insert(manual_adjustment).values(**adjustment))
            target = manual_adjustment.c.id == adjustment["id"]

            def change(**values: Any) -> Executable:
                return update(manual_adjustment).where(target).values(**values)

            for status in statuses:
                session.execute(change(status=status))
            return change

        def refused(change: Callable[..., Executable], old: str, new: str) -> None:
            assert _fails(session, change(status=new)) == (
                "P0001",
                f"EREV-TRN-001: status of erev.manual_adjustment cannot change from {old} to {new}",
            )

        withdrawn = fresh("SUBMITTED", "DRAFT")
        session.execute(withdrawn(memo="Edited after the withdrawal."))  # a draft again
        session.execute(withdrawn(status="SUBMITTED"))
        session.execute(withdrawn(status="REJECTED"))
        assert _fails(session, withdrawn(memo="Edited while rejected")) == (
            "P0001",
            "EREV-TRN-001: columns memo of erev.manual_adjustment cannot change",
        )
        refused(withdrawn, "REJECTED", "SUBMITTED")
        refused(withdrawn, "REJECTED", "VOIDED")
        session.execute(withdrawn(status="DRAFT"))  # revise ...
        session.execute(withdrawn(memo="Revised after the rejection."))
        session.execute(withdrawn(status="VOIDED"))  # ... or discard
        refused(withdrawn, "VOIDED", "DRAFT")
        refused(withdrawn, "VOIDED", "SUBMITTED")

        refused(fresh("SUBMITTED"), "SUBMITTED", "VOIDED")
        refused(fresh("SUBMITTED", "APPROVED"), "APPROVED", "DRAFT")
        posted = fresh("SUBMITTED", "APPROVED", "POSTED")
        refused(posted, "POSTED", "DRAFT")
        session.execute(posted(status="VOIDED"))  # through an approved reversal (SM-10)


def test_db_03_journal_and_adjustment_transitions(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-03 (CLO-1): a manual adjustment is editable while DRAFT and then changes along SM-10 with
    # its listed columns; runs and batches change state along E-34 with set-once instants; an
    # unlisted column is not granted (42501).
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        ledger = insert_ledger_parts(session, tenant_id)
        adjustment = manual_adjustment_values(
            tenant_id,
            contract_id=ledger.chain.contract_id,
            entity_id=ledger.chain.entity_id,
            period_id=ledger.period_id,
        )
        session.execute(insert(manual_adjustment).values(**adjustment))
        target = manual_adjustment.c.id == adjustment["id"]

        def change(**values: Any) -> Executable:
            return update(manual_adjustment).where(target).values(**values)

        session.execute(change(memo="Reclass of the probe release."))
        session.execute(change(status="SUBMITTED", content_sha256="0" * 64))
        assert _fails(session, change(memo="Later")) == (
            "P0001",
            "EREV-TRN-001: columns memo of erev.manual_adjustment cannot change",
        )
        assert _fails(session, change(status="POSTED")) == (
            "P0001",
            "EREV-TRN-001: status of erev.manual_adjustment cannot change from SUBMITTED to POSTED",
        )
        assert _fails(session, change(contract_id=new_id()))[0] == "42501"
        session.execute(change(status="APPROVED", is_deferred_past_lock=True))
        session.execute(change(status="POSTED"))

        rows = insert_journal_rows(session, tenant_id)
        run = journal_run.c.id == rows.run["id"]
        assert _fails(session, update(journal_run).where(run).values(state="exported")) == (
            "P0001",
            "EREV-TRN-001: state of erev.journal_run cannot change from draft to exported",
        )
        session.execute(
            update(journal_run).where(run).values(state="approved", approved_at=APPROVED_AT)
        )
        later = update(journal_run).where(run).values(approved_at=APPROVED_AT + timedelta(1))
        assert _fails(session, later) == (
            "P0001",
            "EREV-TRN-001: approved_at of erev.journal_run is already set",
        )
        session.execute(
            update(journal_run).where(run).values(state="cancelled", cancelled_at=APPROVED_AT)
        )
        assert _fails(session, _move_batch(rows, "acknowledged")) == (
            "P0001",
            "EREV-TRN-001: state of erev.journal_batch cannot change from draft to acknowledged",
        )
        session.execute(_move_batch(rows, "approved"))
        session.execute(_move_batch(rows, "exported", exported_at=APPROVED_AT, attempt_count=1))
        session.execute(_move_batch(rows, "failed", last_error="ERP timeout"))
        session.execute(_move_batch(rows, "exported", attempt_count=2))
        session.execute(_move_batch(rows, "acknowledged", acknowledged_at=APPROVED_AT))
        assert _fails(session, _move_batch(rows, "exported")) == (
            "P0001",
            "EREV-TRN-001: state of erev.journal_batch cannot change from acknowledged to exported",
        )
        assert _fails(session, _move_batch(rows, "acknowledged", external_id="erev:x"))[0] == (
            "42501"
        )


def test_db_15_snapshot_target_must_be_sandbox(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DB-15 (SNP-1; REQ-PLT-024; CTL-043): tenant_snapshot.target_tenant_id names a sandbox tenant
    # the invoker can see, else EREV-SBX-001 (P0001). The trigger reads erev.tenant as the invoker
    # under RLS-TN, which reveals the current tenant, the actor's ACTIVE memberships and the
    # read-only tenant_directory scope only (04 rev 1.56; provisioning reveals nothing). The actor
    # therefore holds memberships of both production tenants — the wrong-kind refusal is a
    # visible-wrong-kind case — and joins the sandbox only for the positive path; a sandbox the
    # actor is no member of is refused as hidden. Written in slice I-1; rewritten after the
    # integrated batch on main 0cb36c14 refused the provisioning-scope path; NOT RUN on the lane
    # (databases erev_rv_l23_* are Ray-side) — see the lane record §13.1, §13.4.13.
    from support.rows import insert_sandbox_tenant, membership_row, tenant_snapshot_values

    production = tenant_id_of(tenant_factory(keyring=keyring))
    other_production = tenant_id_of(tenant_factory(keyring=keyring))
    sandbox = insert_sandbox_tenant(keyring)
    with identity_session(request_id="tests-db-15-user") as session:
        user_id = insert_app_user(session)

    def join(tenant_id: UUID) -> None:
        with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as db:
            db.execute(
                insert(tenant_membership).values(
                    **membership_row(RowContext(tenant_id, user_id), status=MembershipStatus.ACTIVE)
                )
            )

    join(production)
    join(other_production)
    actor = DbContext(tenant_id=production, user_id=user_id, entity_scope="*")
    row = tenant_snapshot_values(production)

    def target(tenant_id: UUID) -> Executable:
        return (
            update(tenant_snapshot)
            .where(tenant_snapshot.c.id == row["id"])
            .values(target_tenant_id=tenant_id)
        )

    with tenant_session(actor) as session:
        session.execute(insert(tenant_snapshot).values(**row))
        # a production tenant the actor can see is refused for its kind
        state, message = _fails(session, target(other_production))
        assert state == "P0001" and "of kind production" in message
        # a sandbox the actor is no member of is hidden by RLS-TN and refused as such
        state, message = _fails(session, target(sandbox))
        assert state == "P0001" and "unknown or hidden" in message
    # the sandbox target succeeds once the actor holds an ACTIVE membership of the sandbox
    join(sandbox)
    with tenant_session(actor) as session:
        session.execute(target(sandbox))
    with tenant_session(
        DbContext(tenant_id=production, user_id=None, entity_scope="*"), read_only=True
    ) as session:
        stored = session.execute(
            select(tenant_snapshot.c.target_tenant_id).where(tenant_snapshot.c.id == row["id"])
        ).scalar_one()
    assert stored == sandbox


@pytest.mark.control("CTL-015")
def test_ctl_015_after_lock_inserts_refused(
    committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    # CTL-015 (J-13-AC-5; BUILD_SPEC CLO-6): after a period is locked through the lock's own writer
    # (``_persist_lock``, D-98 61: an APPROVED PERIOD_LOCK request, the period_lock row, then the
    # closing → closed T-REF-07 row naming both — its CHECKs require both references for
    # ``closed``; Codex CLO6-R3 (4)), inserts of journal_line and subledger_line for that period
    # raise EREV-LED-003 (DB-07). NOT RUN on the authoring worktree (databases not provisioned).
    from erev_api.db.tables import approval_request, contract_computation, engine_release
    from erev_api.domain.close import commands as close_commands
    from erev_api.domain.close import gates as close_gates
    from erev_api.enums import LockKind, PeriodState
    from sqlalchemy import and_
    from support.rows import (
        ContractRows,
        LedgerParts,
        approval_request_values,
        contract_computation_values,
        contract_values,
        engine_release_values,
    )

    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        rows = insert_journal_rows(session, tenant_id, lines=(), state="closing")
        parts = rows.parts
        state = (
            session.execute(
                select(period_state).where(
                    period_state.c.entity_id == parts.entity_id,
                    period_state.c.period_id == parts.period_id,
                )
            )
            .mappings()
            .one()
        )
    ctx = RequestContext(
        principal=system_principal(tenant_id),
        tenant_kind=TenantKind.PRODUCTION,
        request_id="tests-ctl-015-lock",
        source_ip=None,
        user_agent=None,
        idempotency_key=None,
        if_match=None,
        now=clock.now(),
        format_locale="en-US",
    )
    files = LocalFileStore(app_settings.file_root)
    with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
        scope = close_gates.period_scope(uow.session, UUID(str(state["id"])), lock=True)
        assert scope is not None and scope.state == PeriodState.CLOSING.value
        request = approval_request_values(
            tenant_id,
            status=ApprovalRequestStatus.APPROVED,
            entity_id=parts.entity_id,
            subject_type="PERIOD_LOCK",
            subject_id=scope.state_id,
            summary="Lock FY2026-P01 for the CTL-015 probe",
        )
        uow.session.execute(insert(approval_request).values(**request))
        close_commands._persist_lock(
            uow,
            scope,
            kind=LockKind.LOCK,
            lock_id=new_id(),
            transition_id=new_id(),
            from_state=PeriodState.CLOSING,
            to_state=PeriodState.CLOSED,
            action=close_commands.LOCK_ACTION,
            approval_request_id=UUID(str(request["id"])),
            comment="Locked for the CTL-015 probe",
            certification=[],
            snapshot_manifest_sha256=None,
            heads=close_commands._heads(uow.session, scope),
            cutoff_known_at=uow.now,  # 04 T-CLS-04 rev 1.113 (R-40 (c)): a LOCK names its cutoff
        )
        uow.commit()
    with tenant_session(context) as session:
        line = journal_line_values(
            tenant_id,
            parts=parts,
            entry_id=rows.entries[0]["id"],
            batch_id=rows.batch["id"],
            line_no=9,
            period_id=parts.period_id,
        )
        sqlstate, message = _fails(session, insert(journal_line).values(**line))
        assert (sqlstate, message.startswith("EREV-LED-003")) == ("P0001", True), message
        # (a) Genuine ledger parts bound to the SAME locked legal entity, book and period, built
        # against the EXISTING entity — never reinserted, no swallowed setup error (Codex 0214: the
        # v1 `insert_contract_rows(entity_id=<existing>)` reinserted it and `_insert_visible`
        # returned a fresh UNINSERTED id); the entity-reuse shape follows B4's sprint/l6 7092122a.
        # The persisted chain is bound to the lock by a positive read before the probe: the contract
        # contracts with the locked entity and (entity, ASC606, period) is `closed`.
        # (b) Every fixture row of the probe lives in one encompassing savepoint rolled back after
        # the expected refusals, so the unsealed posting never reaches 0040's deferred seal guard at
        # commit; the lock committed above is untouched and re-read afterwards.
        probe = session.begin_nested()
        buyer = customer_values(tenant_id)
        session.execute(insert(customer).values(**buyer))
        group = combination_group_values(tenant_id)
        session.execute(insert(combination_group).values(**group))
        row = contract_values(
            tenant_id,
            customer_id=buyer["id"],
            contracting_entity_id=parts.entity_id,
            combination_group_id=group["id"],
            head_stream_version=1,
        )
        session.execute(insert(contract).values(**row))
        release = engine_release_values()
        session.execute(insert(engine_release).values(**release))
        computation = contract_computation_values(
            tenant_id, combination_group_id=group["id"], engine_release_id=release["id"]
        )
        session.execute(insert(contract_computation).values(**computation))
        bound = session.execute(
            select(contract.c.contracting_entity_id, period_state.c.state, period.c.end_date)
            .select_from(
                contract.join(
                    period_state,
                    and_(
                        period_state.c.entity_id == contract.c.contracting_entity_id,
                        period_state.c.period_id == parts.period_id,
                        period_state.c.book_code == "ASC606",
                    ),
                ).join(period, period.c.id == period_state.c.period_id)
            )
            .where(contract.c.id == row["id"])
        ).one()
        assert (UUID(str(bound.contracting_entity_id)), str(bound.state)) == (
            parts.entity_id,
            PeriodState.CLOSED.value,
        )
        ledger = LedgerParts(
            chain=ContractRows(
                entity_id=parts.entity_id,
                customer_id=UUID(str(buyer["id"])),
                group_id=UUID(str(group["id"])),
                contract_id=UUID(str(row["id"])),
            ),
            computation_id=UUID(str(computation["id"])),
            period_id=parts.period_id,
            period_end_date=bound.end_date,
            account_id=parts.account_id,
        )
        posting = subledger_posting_values(tenant_id, parts=ledger)
        session.execute(insert(subledger_posting).values(**posting))
        subledger = subledger_line_values(tenant_id, posting=posting, parts=ledger)
        sqlstate, message = _fails(session, insert(subledger_line).values(**subledger))
        assert (sqlstate, message.startswith("EREV-LED-003")) == ("P0001", True), message
        probe.rollback()
        # The lock the probe met is the one committed above, still in place after the rollback.
        still_locked = session.execute(
            select(period_state.c.state).where(
                period_state.c.entity_id == parts.entity_id,
                period_state.c.period_id == parts.period_id,
                period_state.c.book_code == "ASC606",
            )
        ).scalar_one()
        assert str(still_locked) == PeriodState.CLOSED.value


def test_db_15_inbound_connection_active_in_sandbox_rejected(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    """DB-15 ``tg_integration_connection__sandbox`` (04 §14.1; T-INT-01 ``status`` note; BUILD_SPEC
    DIN-12 named case): activating an outbound adapter other than ``CSV_GL`` in a sandbox tenant
    raises ``EREV-SBX-001``; an inbound adapter, a CSV_GL export and a production tenant are
    free."""
    sandbox = insert_sandbox_tenant(keyring)
    production = tenant_id_of(tenant_factory(keyring=keyring))
    with tenant_session(DbContext(tenant_id=sandbox, user_id=None, entity_scope="*")) as session:
        for adapter, direction in (("NETSUITE", "OUTBOUND"), ("QUICKBOOKS_ONLINE", "BOTH")):
            savepoint = session.begin_nested()
            with pytest.raises(exc.DBAPIError) as excinfo:
                session.execute(
                    insert(integration_connection).values(
                        **integration_connection_values(
                            sandbox, adapter=adapter, direction=direction, status="ACTIVE"
                        )
                    )
                )
            savepoint.rollback()
            state, message = _error(excinfo)
            assert state == "P0001" and message.startswith("EREV-SBX-001: connection ")
            assert f"cannot activate outbound adapter {adapter}" in message
        # DISABLED first, ACTIVE on UPDATE: the trigger fires BEFORE INSERT OR UPDATE.
        disabled = integration_connection_values(sandbox, adapter="NETSUITE", direction="OUTBOUND")
        session.execute(insert(integration_connection).values(**disabled))
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as excinfo:
            session.execute(
                update(integration_connection)
                .where(integration_connection.c.id == disabled["id"])
                .values(status="ACTIVE")
            )
        savepoint.rollback()
        assert _error(excinfo)[1].startswith("EREV-SBX-001")
        # Free: an inbound CRM connection and the CSV_GL export of a sandbox.
        session.execute(
            insert(integration_connection).values(
                **integration_connection_values(sandbox, status="ACTIVE")  # SALESFORCE INBOUND
            )
        )
        session.execute(
            insert(integration_connection).values(
                **integration_connection_values(
                    sandbox, adapter="CSV_GL", direction="OUTBOUND", status="ACTIVE"
                )
            )
        )
    with tenant_session(DbContext(tenant_id=production, user_id=None, entity_scope="*")) as session:
        session.execute(
            insert(integration_connection).values(
                **integration_connection_values(
                    production, adapter="NETSUITE", direction="OUTBOUND", status="ACTIVE"
                )
            )
        )


def test_db_15_webhook_endpoint_cannot_become_active_in_sandbox(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    """DB-15 ``tg_webhook_endpoint__sandbox`` (04 §14.1 rev 1.125; revision 0091; BUILD_SPEC
    SNP-4; security finding SF-1): in a sandbox tenant an endpoint row cannot become active —
    inserted ``is_active = true``, or updated from false to true — ``EREV-SBX-001``. A row that is
    not active, its other columns, a deactivation and a production tenant are free; a row that is
    already active (written with the trigger off by the schema owner) can still be edited and
    switched off, because the trigger refuses the activation and not the state."""
    from erev_api.db.tables import webhook_endpoint
    from support.rows import webhook_endpoint_values

    sandbox = insert_sandbox_tenant(keyring)
    production = tenant_id_of(tenant_factory(keyring=keyring))
    trigger = "tg_webhook_endpoint__sandbox"

    def endpoint(tenant_id: UUID, **values: Any) -> Executable:
        return insert(webhook_endpoint).values(**{**webhook_endpoint_values(tenant_id), **values})

    def change(endpoint_id: UUID, **values: Any) -> Executable:
        return update(webhook_endpoint).where(webhook_endpoint.c.id == endpoint_id).values(**values)

    with tenant_session(DbContext(tenant_id=sandbox, user_id=None, entity_scope="*")) as session:
        # The column default is true, so an INSERT that does not name it is refused as well.
        for statement in (endpoint(sandbox), endpoint(sandbox, is_active=True)):
            state, message = _fails(session, statement)
            assert state == "P0001", message
            assert message.startswith("EREV-SBX-001: webhook endpoint "), message
            assert message.endswith("cannot be active; a sandbox sends no webhooks"), message
        stored = webhook_endpoint_values(sandbox)
        session.execute(insert(webhook_endpoint).values(**stored, is_active=False))
        state, message = _fails(session, change(stored["id"], is_active=True))
        assert state == "P0001" and message.startswith("EREV-SBX-001"), message
        assert str(stored["id"]) in message
        # Free: the other columns of an inactive row, and naming the flag without changing it.
        session.execute(change(stored["id"], description="kept for reference", is_active=False))
    owner = committed_db.owner_engine
    with owner.begin() as connection:
        connection.exec_driver_sql(f"ALTER TABLE erev.webhook_endpoint DISABLE TRIGGER {trigger}")
    try:
        with tenant_session(
            DbContext(tenant_id=sandbox, user_id=None, entity_scope="*")
        ) as session:
            legacy = webhook_endpoint_values(sandbox)
            session.execute(insert(webhook_endpoint).values(**legacy))
    finally:
        with owner.begin() as connection:
            connection.exec_driver_sql(
                f"ALTER TABLE erev.webhook_endpoint ENABLE TRIGGER {trigger}"
            )
    with tenant_session(DbContext(tenant_id=sandbox, user_id=None, entity_scope="*")) as session:
        session.execute(change(legacy["id"], description="from before the rule"))
        session.execute(change(legacy["id"], is_active=False))
        state, message = _fails(session, change(legacy["id"], is_active=True))
        assert state == "P0001" and message.startswith("EREV-SBX-001"), message
        rows = dict(
            session.execute(select(webhook_endpoint.c.id, webhook_endpoint.c.is_active)).all()
        )
    assert rows == {stored["id"]: False, legacy["id"]: False}
    with tenant_session(DbContext(tenant_id=production, user_id=None, entity_scope="*")) as session:
        live = webhook_endpoint_values(production)
        session.execute(insert(webhook_endpoint).values(**live))
        session.execute(change(live["id"], is_active=False))
        session.execute(change(live["id"], is_active=True))
        assert session.execute(
            select(webhook_endpoint.c.is_active).where(webhook_endpoint.c.id == live["id"])
        ).scalar_one()


def test_task_signature_cycles_preserve_other_uniqueness_and_refuse_lossy_downgrade(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    fresh_head()
    from importlib import import_module

    migration = import_module("erev_api.db.migrations.versions.0135_close_task_signoffs")
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    with identity_session(request_id="tests-task-signature-cycles") as session:
        preparer = insert_app_user(session)
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    subject_id = new_id()
    with tenant_session(context) as session:

        def signed(subject_type: str, digest: str) -> Executable:
            return insert(signoff).values(
                **signoff_values(
                    tenant_id,
                    subject_id=subject_id,
                    signer_id=preparer,
                    subject_type=subject_type,
                    subject_content_sha256=digest,
                )
            )

        session.execute(signed("close_checklist_item", "a" * 64))
        assert _fails(session, signed("close_checklist_item", "a" * 64))[0] == "23505"
        session.execute(signed("close_checklist_item", "b" * 64))
        session.execute(signed("reconciliation", "a" * 64))
        assert _fails(session, signed("reconciliation", "b" * 64))[0] == "23505"
    # The owner has no tenant context and no BYPASSRLS: the migration must see all histories.
    with committed_db.owner_engine.connect() as connection:
        transaction = connection.begin()
        try:
            with (
                ops.bound_to(connection),
                pytest.raises(sa.exc.DBAPIError, match="repeated task signoffs"),
            ):
                migration.downgrade()
        finally:
            transaction.rollback()
        assert (
            connection.exec_driver_sql(
                "SELECT relforcerowsecurity FROM pg_class WHERE oid = 'erev.signoff'::regclass"
            ).scalar_one()
            is True
        )
    with tenant_session(context, read_only=True) as session:
        assert (
            session.execute(
                select(func.count()).select_from(signoff).where(signoff.c.subject_id == subject_id)
            ).scalar_one()
            == 3
        )
