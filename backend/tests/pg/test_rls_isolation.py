"""RLS isolation DG-TST-20 (04 §1.4 RLS-T, RLS-TN, RLS-TM; REQ-PLT-001, REQ-PLT-002; PLF-1).

``test_ctl_036_cross_tenant_isolation`` runs every ``ROW_BUILDERS`` table, and
``test_row_builders_complete`` ties that set to the catalogue, so together they cover every table
of schema erev with a ``tenant_id`` column (SPEC-Q-119).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.db import new_id
from erev_api.db.lint import GLOBAL_TABLES
from erev_api.db.session import (
    DbContext,
    identity_session,
    of_session_tenant,
    platform_session,
    tenant_session,
)
from erev_api.db.tables import (
    app_user,
    close_checklist_template,
    close_run,
    disclosure_snapshot,
    fiscal_calendar,
    journal_line,
    legal_entity,
    metadata,
    period,
    period_state,
    reconciliation,
    report_definition,
    schedule,
    subledger_line,
    tenant_membership,
)
from erev_api.db.tables import tenant as tenant_table
from erev_api.enums import MembershipStatus
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
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import (
    PROVISIONED_TABLES,
    ROW_BUILDERS,
    ROW_COMPLETERS,
    CloseParts,
    ContractRows,
    JournalRows,
    RowContext,
    approval_request_values,
    close_checklist_item_values,
    close_checklist_template_values,
    close_run_values,
    contract_event_values,
    contract_values,
    contract_version_balance_values,
    disclosure_snapshot_values,
    entity_book_values,
    event_submission_values,
    fiscal_calendar_values,
    insert_app_user,
    insert_close_parts,
    insert_contract_rows,
    insert_journal_rows,
    insert_ledger_parts,
    insert_ledger_rows,
    insert_report_run,
    insert_version_rows,
    journal_line_values,
    legal_entity_values,
    manual_adjustment_values,
    membership_row,
    period_lock_values,
    period_state_transition_values,
    period_state_values,
    period_values,
    reconciliation_values,
    schedule_line_values,
    schedule_values,
    subledger_line_values,
)

pytestmark = pytest.mark.pg

INSUFFICIENT_PRIVILEGE = "42501"
_TENANT_TABLES = text(
    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'erev' AND c.relkind IN ('r', 'p') AND NOT c.relispartition "
    "AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid "
    "AND a.attname = 'tenant_id' AND NOT a.attisdropped) ORDER BY 1"
)


def tenant_tables(bind: Session | Connection) -> list[str]:
    """Tables of schema erev with ``tenant_id``, less the RLS-NONE-U tables of the DB-14 list."""
    return [str(name) for (name,) in bind.execute(_TENANT_TABLES) if name not in GLOBAL_TABLES]


@dataclass(frozen=True, slots=True)
class Tenants:
    a: UUID
    b: UUID
    user_id: UUID


def _all_entities(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _outcome(session: Session, statement: Executable) -> int | str:
    """Rows affected, or the SQLSTATE of the failure; a failure rolls back its savepoint only."""
    savepoint = session.begin_nested()
    try:
        result = cast(CursorResult[Any], session.execute(statement))
    except exc.DBAPIError as error:
        savepoint.rollback()
        return str(getattr(error.orig, "sqlstate", None))
    savepoint.commit()
    return result.rowcount


@pytest.fixture
def two_tenants(committed_db: TestDatabase, keyring: KeyRing) -> Tenants:
    a = tenant_id_of(tenant_factory(keyring=keyring))
    b = tenant_id_of(tenant_factory(keyring=keyring))
    with identity_session(request_id="tests-rls-user") as session:
        user_id = insert_app_user(session)
    return Tenants(a=a, b=b, user_id=user_id)


@pytest.mark.control("CTL-036")
@pytest.mark.parametrize("table_name", sorted(ROW_BUILDERS))
def test_ctl_036_cross_tenant_isolation(table_name: str, two_tenants: Tenants) -> None:
    table = metadata.tables[f"erev.{table_name}"]
    build = ROW_BUILDERS[table_name]
    a, b, user_id = two_tenants.a, two_tenants.b, two_tenants.user_id
    inserted: dict[UUID, dict[str, Any]] = {}
    for tenant_id in (a, b):
        with tenant_session(_all_entities(tenant_id)) as session:
            row = build(RowContext(tenant_id, user_id), session)
            if table_name not in PROVISIONED_TABLES:
                session.execute(insert(table).values(**row))
                complete = ROW_COMPLETERS.get(table_name)
                if complete is not None:
                    complete(RowContext(tenant_id, user_id), session, row)
        inserted[tenant_id] = row

    def count(*tenants: UUID) -> Executable:
        return select(func.count()).select_from(table).where(table.c.tenant_id.in_(tenants))

    with tenant_session(_all_entities(a)) as session:
        # Provisioned tenants hold other rows too (the admin membership, the first audit event),
        # so match the row by its primary key.
        key = [column == inserted[a][column.name] for column in table.primary_key.columns]
        own = select(func.count()).select_from(table).where(*key)
        assert session.execute(own).scalar_one() == 1
        # (a) B rows are invisible.
        assert session.execute(count(b)).scalar_one() == 0
        # (b) a B row cannot be inserted.
        stray = insert(table).values(**build(RowContext(b, user_id), session))
        assert _outcome(session, stray) == INSUFFICIENT_PRIVILEGE
        # (c) and (d): B rows are neither updated nor deleted.
        touch_b = update(table).where(table.c.tenant_id == b).values(tenant_id=table.c.tenant_id)
        assert _outcome(session, touch_b) in (0, INSUFFICIENT_PRIVILEGE)
        remove_b = delete(table).where(table.c.tenant_id == b)
        assert _outcome(session, remove_b) in (0, INSUFFICIENT_PRIVILEGE)

    # (e) without tenant context nothing is visible and nothing can be inserted.
    with identity_session(request_id="tests-ctl-036-no-context") as session:
        assert session.execute(count(a, b)).scalar_one() == 0
        orphan = insert(table).values(**build(RowContext(a, user_id), session))
        assert _outcome(session, orphan) == INSUFFICIENT_PRIVILEGE


E1 = UUID("0191e0a0-0000-7000-8000-0000000000e1")
E2 = UUID("0191e0a0-0000-7000-8000-0000000000e2")


def test_rls_te_approval_request_entity_scope(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DG-TST-20 (f): a context scoped to E1 neither sees nor inserts E2 rows; a request without an
    # entity is tenant-wide and visible to every scope (04 T-PLT-17).
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    table = metadata.tables["erev.approval_request"]
    rows = {
        name: approval_request_values(tenant_id, entity_id=entity)
        for name, entity in (("e1", E1), ("e2", E2), ("tenant", None))
    }
    with tenant_session(_all_entities(tenant_id)) as session:
        for row in rows.values():
            session.execute(insert(table).values(**row))
    ids = [row["id"] for row in rows.values()]
    with tenant_session(
        DbContext(tenant_id=tenant_id, user_id=None, entity_scope=(E1,))
    ) as session:
        visible = set(session.scalars(select(table.c.id).where(table.c.id.in_(ids))))
        assert visible == {rows["e1"]["id"], rows["tenant"]["id"]}
        stray = insert(table).values(**approval_request_values(tenant_id, entity_id=E2))
        assert _outcome(session, stray) == INSUFFICIENT_PRIVILEGE
        own = approval_request_values(tenant_id, entity_id=E1)
        session.execute(insert(table).values(**own))
        inserted = select(func.count()).select_from(table).where(table.c.id == own["id"])
        assert session.execute(inserted).scalar_one() == 1


RLS_TE_TABLES = ("legal_entity", "entity_book", "period_state", "period_state_transition")


@pytest.mark.parametrize("table_name", RLS_TE_TABLES)
def test_rls_te_entity_scope(table_name: str, committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DG-TST-20 (f) for the RLS-TE tables of RFD-2 (REQ-PLT-012): a context scoped to E1 and E3
    # neither sees nor inserts E2 rows, and inserts a row of E3.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    table = metadata.tables[f"erev.{table_name}"]
    e1, e2, e3 = new_id(), new_id(), new_id()
    calendar = fiscal_calendar_values(tenant_id)
    january = period_values(tenant_id, calendar_id=calendar["id"])
    states: dict[UUID, UUID] = {}

    def values(entity_id: UUID) -> dict[str, Any]:
        match table_name:
            case "legal_entity":
                return legal_entity_values(
                    tenant_id, calendar_id=calendar["id"], entity_id=entity_id
                )
            case "entity_book":
                return entity_book_values(
                    tenant_id, entity_id=entity_id, first_period_id=january["id"]
                )
            case "period_state":
                return period_state_values(tenant_id, entity_id=entity_id, period_id=january["id"])
            case _:
                return period_state_transition_values(
                    tenant_id,
                    period_state_id=states[entity_id],
                    entity_id=entity_id,
                    period_id=january["id"],
                )

    rows: dict[UUID, UUID] = {}
    with tenant_session(_all_entities(tenant_id)) as session:
        session.execute(insert(fiscal_calendar).values(**calendar))
        session.execute(insert(period).values(**january))
        # The E3 entity of a legal_entity case is the row the scoped context inserts.
        kept = (e1, e2) if table_name == "legal_entity" else (e1, e2, e3)
        for entity_id in kept:
            entity = legal_entity_values(tenant_id, calendar_id=calendar["id"], entity_id=entity_id)
            session.execute(insert(legal_entity).values(**entity))
        if table_name == "period_state_transition":
            for entity_id in kept:
                state = period_state_values(tenant_id, entity_id=entity_id, period_id=january["id"])
                session.execute(insert(period_state).values(**state))
                states[entity_id] = state["id"]
        for entity_id in (e1, e2):
            if table_name == "legal_entity":
                rows[entity_id] = entity_id
                continue
            row = values(entity_id)
            session.execute(insert(table).values(**row))
            rows[entity_id] = row["id"]

    scoped = DbContext(tenant_id=tenant_id, user_id=None, entity_scope=(e1, e3))
    with tenant_session(scoped) as session:
        visible = set(
            session.scalars(select(table.c.id).where(table.c.id.in_(list(rows.values()))))
        )
        assert visible == {rows[e1]}
        outside = new_id() if table_name == "legal_entity" else e2
        assert _outcome(session, insert(table).values(**values(outside))) == INSUFFICIENT_PRIVILEGE
        own = values(e3)
        session.execute(insert(table).values(**own))
        inserted = select(func.count()).select_from(table).where(table.c.id == own["id"])
        assert session.execute(inserted).scalar_one() == 1


CONTRACT_RLS_TE_TABLES = ("contract", "contract_event", "event_submission")


@pytest.mark.parametrize("table_name", CONTRACT_RLS_TE_TABLES)
def test_rls_te_contract_entity_scope(
    table_name: str, committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DG-TST-20 (f) for the RLS-TE tables of CTR-1 on contracting_entity_id (REQ-PLT-012): a context
    # scoped to E1 and E3 neither sees nor inserts E2 rows, and inserts a row of E3. The DB-08
    # trigger leaves an event outside the scope to row-level security.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    table = metadata.tables[f"erev.{table_name}"]
    e1, e2, e3 = new_id(), new_id(), new_id()

    def values(chain: ContractRows) -> dict[str, Any]:
        match table_name:
            case "contract":
                return contract_values(
                    tenant_id,
                    customer_id=chain.customer_id,
                    contracting_entity_id=chain.entity_id,
                    combination_group_id=chain.group_id,
                )
            case "contract_event":
                return contract_event_values(
                    tenant_id,
                    contract_id=chain.contract_id,
                    contracting_entity_id=chain.entity_id,
                    stream_version=1,
                )
            case _:
                return event_submission_values(
                    tenant_id, contract_id=chain.contract_id, contracting_entity_id=chain.entity_id
                )

    rows: dict[UUID, UUID] = {}
    with tenant_session(_all_entities(tenant_id)) as session:
        chains = {
            entity: insert_contract_rows(
                session, tenant_id, head_stream_version=1, entity_id=entity
            )
            for entity in (e1, e2, e3)
        }
        for entity in (e1, e2):
            if table_name == "contract":
                rows[entity] = chains[entity].contract_id
                continue
            row = values(chains[entity])
            session.execute(insert(table).values(**row))
            rows[entity] = row["id"]

    scoped = DbContext(tenant_id=tenant_id, user_id=None, entity_scope=(e1, e3))
    with tenant_session(scoped) as session:
        visible = set(
            session.scalars(select(table.c.id).where(table.c.id.in_(list(rows.values()))))
        )
        assert visible == {rows[e1]}
        stray = insert(table).values(**values(chains[e2]))
        assert _outcome(session, stray) == INSUFFICIENT_PRIVILEGE
        own = values(chains[e3])
        session.execute(insert(table).values(**own))
        inserted = select(func.count()).select_from(table).where(table.c.id == own["id"])
        assert session.execute(inserted).scalar_one() == 1


COMPUTED_RLS_TE_TABLES = ("contract_version_balance", "schedule_line")


@pytest.mark.parametrize("table_name", COMPUTED_RLS_TE_TABLES)
def test_rls_te_computed_entity_scope(
    table_name: str, committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DG-TST-20 (f) for the RLS-TE tables of CTR-2 on entity_id (REQ-PLT-012): a context scoped to
    # E1 and E3 neither sees nor inserts E2 rows, and inserts a row of E3.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    table = metadata.tables[f"erev.{table_name}"]
    e1, e2, e3 = new_id(), new_id(), new_id()
    parents: dict[UUID, dict[str, UUID]] = {}

    def values(entity: UUID) -> dict[str, Any]:
        found = parents[entity]
        if table_name == "contract_version_balance":
            return contract_version_balance_values(
                tenant_id,
                contract_version_id=found["version_id"],
                contract_id=found["contract_id"],
                entity_id=entity,
            )
        return schedule_line_values(
            tenant_id,
            schedule_id=found["schedule_id"],
            contract_version_id=found["version_id"],
            contract_id=found["contract_id"],
            entity_id=entity,
            period_id=found["period_id"],
        )

    rows: dict[UUID, UUID] = {}
    with tenant_session(_all_entities(tenant_id)) as session:
        for entity in (e1, e2, e3):
            version = insert_version_rows(session, tenant_id, entity_id=entity)
            header = schedule_values(
                tenant_id,
                contract_version_id=version.version_id,
                combination_group_id=version.chain.group_id,
            )
            session.execute(insert(schedule).values(**header))
            calendar_id = session.execute(
                select(legal_entity.c.calendar_id).where(legal_entity.c.id == entity)
            ).scalar_one()
            january = period_values(tenant_id, calendar_id=calendar_id)
            session.execute(insert(period).values(**january))
            parents[entity] = {
                "version_id": version.version_id,
                "contract_id": version.chain.contract_id,
                "schedule_id": header["id"],
                "period_id": january["id"],
            }
        for entity in (e1, e2):
            row = values(entity)
            session.execute(insert(table).values(**row))
            rows[entity] = row["id"]

    scoped = DbContext(tenant_id=tenant_id, user_id=None, entity_scope=(e1, e3))
    with tenant_session(scoped) as session:
        visible = set(
            session.scalars(select(table.c.id).where(table.c.id.in_(list(rows.values()))))
        )
        assert visible == {rows[e1]}
        assert _outcome(session, insert(table).values(**values(e2))) == INSUFFICIENT_PRIVILEGE
        own = values(e3)
        session.execute(insert(table).values(**own))
        inserted = select(func.count()).select_from(table).where(table.c.id == own["id"])
        assert session.execute(inserted).scalar_one() == 1


def test_rls_te_subledger_line_entity_scope(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DG-TST-20 (f) for T-SL-04 on entity_id (CTR-3; REQ-PLT-012): a context scoped to E1 and E3
    # neither sees nor inserts E2 lines, and posts a sealed posting of E3. The DB-06 and DB-07
    # triggers leave a line outside the scope to row-level security.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    e1, e2, e3 = new_id(), new_id(), new_id()
    with tenant_session(_all_entities(tenant_id)) as session:
        own = insert_ledger_rows(session, tenant_id, entity_id=e1)
        other = insert_ledger_rows(session, tenant_id, entity_id=e2)

    scoped = DbContext(tenant_id=tenant_id, user_id=None, entity_scope=(e1, e3))
    with tenant_session(scoped) as session:
        ids = [line["id"] for line in (*own.lines, *other.lines)]
        visible = set(
            session.scalars(select(subledger_line.c.id).where(subledger_line.c.id.in_(ids)))
        )
        assert visible == {line["id"] for line in own.lines}
        stray = subledger_line_values(tenant_id, posting=other.posting, parts=other.parts)
        assert _outcome(session, insert(subledger_line).values(**stray)) == INSUFFICIENT_PRIVILEGE
        mine = insert_ledger_rows(session, tenant_id, entity_id=e3)
        posted = (
            select(func.count())
            .select_from(subledger_line)
            .where(subledger_line.c.subledger_posting_id == mine.posting_id)
        )
        assert session.execute(posted).scalar_one() == 2


def test_rls_te_journal_entity_scope(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DG-TST-20 (f) for T-SL-05 to T-SL-09 on entity_id (CLO-1; REQ-PLT-012): a context scoped to
    # E1, E3 and E5 sees the adjustment, run, batch, entries and lines of E1 and E3 but none of E2
    # and E4, cannot insert an E2 line, and writes a run of E5.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    e1, e2, e3, e4, e5 = (new_id() for _ in range(5))
    adjustments: dict[UUID, UUID] = {}
    with tenant_session(_all_entities(tenant_id)) as session:
        own = insert_journal_rows(session, tenant_id, entity_id=e1)
        other = insert_journal_rows(session, tenant_id, entity_id=e2)
        for entity_id in (e3, e4):
            ledger = insert_ledger_parts(session, tenant_id, entity_id=entity_id)
            row = manual_adjustment_values(
                tenant_id,
                contract_id=ledger.chain.contract_id,
                entity_id=entity_id,
                period_id=ledger.period_id,
            )
            session.execute(insert(metadata.tables["erev.manual_adjustment"]).values(**row))
            adjustments[entity_id] = row["id"]

    def ids(rows: JournalRows, adjustment_id: UUID) -> dict[str, set[Any]]:
        return {
            "manual_adjustment": {adjustment_id},
            "journal_run": {rows.run["id"]},
            "journal_batch": {rows.batch["id"]},
            "journal_entry": {entry["id"] for entry in rows.entries},
            "journal_line": {line["id"] for line in rows.lines},
        }

    mine, theirs = ids(own, adjustments[e3]), ids(other, adjustments[e4])
    scoped = DbContext(tenant_id=tenant_id, user_id=None, entity_scope=(e1, e3, e5))
    with tenant_session(scoped) as session:
        for name, own_ids in mine.items():
            table = metadata.tables[f"erev.{name}"]
            candidates = table.c.id.in_(own_ids | theirs[name])
            assert set(session.scalars(select(table.c.id).where(candidates))) == own_ids, name
        stray = journal_line_values(
            tenant_id,
            parts=other.parts,
            entry_id=other.entries[0]["id"],
            batch_id=other.batch["id"],
            line_no=3,
        )
        assert _outcome(session, insert(journal_line).values(**stray)) == INSUFFICIENT_PRIVILEGE
        written = insert_journal_rows(session, tenant_id, entity_id=e5)
        lines = (
            select(func.count())
            .select_from(journal_line)
            .where(journal_line.c.journal_batch_id == written.batch["id"])
        )
        assert session.execute(lines).scalar_one() == 2


def test_rls_te_close_entity_scope(committed_db: TestDatabase, keyring: KeyRing) -> None:
    # DG-TST-20 (f) for T-CLS-01, T-CLS-03, T-CLS-04 and T-CLS-06 on entity_id (CLO-2;
    # REQ-PLT-012): a context scoped to E1 and E3 sees the run, checklist item, lock and
    # reconciliation of E1 but none of E2, cannot insert a run of E2, and writes a reconciliation
    # of E3.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    e1, e2, e3 = new_id(), new_id(), new_id()
    parts: dict[UUID, CloseParts] = {}
    ids: dict[UUID, dict[str, UUID]] = {}
    with tenant_session(_all_entities(tenant_id)) as session:
        template = close_checklist_template_values(tenant_id)
        session.execute(insert(close_checklist_template).values(**template))
        for entity_id in (e1, e2, e3):
            parts[entity_id] = insert_close_parts(session, tenant_id, entity_id=entity_id)
        for entity_id in (e1, e2):
            period_id = parts[entity_id].period_id
            rows = {
                "close_run": close_run_values(tenant_id, entity_id=entity_id, period_id=period_id),
                "close_checklist_item": close_checklist_item_values(
                    tenant_id, template_id=template["id"], entity_id=entity_id, period_id=period_id
                ),
                "period_lock": period_lock_values(tenant_id, parts=parts[entity_id]),
                "reconciliation": reconciliation_values(
                    tenant_id, entity_id=entity_id, period_id=period_id
                ),
            }
            for name, row in rows.items():
                session.execute(insert(metadata.tables[f"erev.{name}"]).values(**row))
            ids[entity_id] = {name: UUID(str(row["id"])) for name, row in rows.items()}

    scoped = DbContext(tenant_id=tenant_id, user_id=None, entity_scope=(e1, e3))
    with tenant_session(scoped) as session:
        for name, own_id in ids[e1].items():
            table = metadata.tables[f"erev.{name}"]
            candidates = table.c.id.in_([own_id, ids[e2][name]])
            assert set(session.scalars(select(table.c.id).where(candidates))) == {own_id}, name
        stray = close_run_values(tenant_id, entity_id=e2, period_id=parts[e2].period_id)
        assert _outcome(session, insert(close_run).values(**stray)) == INSUFFICIENT_PRIVILEGE
        own = reconciliation_values(tenant_id, entity_id=e3, period_id=parts[e3].period_id)
        session.execute(insert(reconciliation).values(**own))
        written = (
            select(func.count()).select_from(reconciliation).where(reconciliation.c.id == own["id"])
        )
        assert session.execute(written).scalar_one() == 1


def test_rls_te_disclosure_snapshot_entity_scope(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    # DG-TST-20 (f) for T-RPT-03 on entity_id (RPS-1; REQ-PLT-012): a context scoped to E1 and E3
    # sees the E1 snapshot but not the E2 snapshot, cannot insert an E2 snapshot, and writes an E3
    # snapshot of the same tenant-wide report run.
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring))
    e1, e2, e3 = new_id(), new_id(), new_id()
    parts: dict[UUID, CloseParts] = {}
    snapshots: dict[UUID, UUID] = {}
    with tenant_session(_all_entities(tenant_id)) as session:
        run_id = insert_report_run(session, tenant_id)
        for entity_id in (e1, e2, e3):
            parts[entity_id] = insert_close_parts(session, tenant_id, entity_id=entity_id)
        for entity_id in (e1, e2):
            row = disclosure_snapshot_values(
                tenant_id,
                entity_id=entity_id,
                period_id=parts[entity_id].period_id,
                report_run_id=run_id,
            )
            session.execute(insert(disclosure_snapshot).values(**row))
            snapshots[entity_id] = UUID(str(row["id"]))

    scoped = DbContext(tenant_id=tenant_id, user_id=None, entity_scope=(e1, e3))
    with tenant_session(scoped) as session:
        candidates = disclosure_snapshot.c.id.in_(list(snapshots.values()))
        visible = set(session.scalars(select(disclosure_snapshot.c.id).where(candidates)))
        assert visible == {snapshots[e1]}
        stray = disclosure_snapshot_values(
            tenant_id, entity_id=e2, period_id=parts[e2].period_id, report_run_id=run_id
        )
        outcome = _outcome(session, insert(disclosure_snapshot).values(**stray))
        assert outcome == INSUFFICIENT_PRIVILEGE
        own = disclosure_snapshot_values(
            tenant_id, entity_id=e3, period_id=parts[e3].period_id, report_run_id=run_id
        )
        session.execute(insert(disclosure_snapshot).values(**own))
        written = (
            select(func.count())
            .select_from(disclosure_snapshot)
            .where(disclosure_snapshot.c.id == own["id"])
        )
        assert session.execute(written).scalar_one() == 1


def test_report_definition_global_catalogue(test_database: TestDatabase) -> None:
    # DB-14 (b) and DG-TST-20 (RPS-1): report_definition has no tenant_id, is on the DB-14
    # allow-list and so stays outside the isolation suite; erev_app reads it without tenant context.
    assert "report_definition" in GLOBAL_TABLES
    assert "tenant_id" not in report_definition.columns
    with identity_session(request_id="tests-rps-1-global-catalogue") as session:
        tables = tenant_tables(session)
        count = select(func.count()).select_from(report_definition)
        assert session.execute(count).scalar_one() == 56
    assert {"report_run", "disclosure_snapshot", "evidence_pack"} <= set(tables)
    assert "report_definition" not in tables


def test_row_builders_complete(test_database: TestDatabase) -> None:
    with identity_session(request_id="tests-row-builders") as session:
        tables = tenant_tables(session)
    assert {"audit_chain_head", "audit_event", "tenant_membership"} <= set(tables)
    missing = sorted(set(tables) - set(ROW_BUILDERS))
    assert missing == [], "tenant tables without a ROW_BUILDERS entry: " + ", ".join(missing)
    assert set(ROW_BUILDERS) <= set(tables)


def test_rls_tn_tenant_visibility(committed_db: TestDatabase, keyring: KeyRing) -> None:
    a, b, c = (tenant_id_of(tenant_factory(keyring=keyring)) for _ in range(3))
    with identity_session(request_id="tests-rls-tn-user") as session:
        user_id = insert_app_user(session)
    for tenant_id, status in (
        (a, MembershipStatus.ACTIVE),
        (b, MembershipStatus.ACTIVE),
        (c, MembershipStatus.INVITED),
    ):
        with tenant_session(_all_entities(tenant_id)) as session:
            row = membership_row(RowContext(tenant_id, user_id), status=status)
            session.execute(insert(tenant_membership).values(**row))

    visible = select(tenant_table.c.id).where(tenant_table.c.id.in_((a, b, c)))
    with tenant_session(_all_entities(a)) as session:
        assert set(session.scalars(visible)) == {a}
    with identity_session(request_id="tests-rls-tn-member", user_id=user_id) as session:
        assert set(session.scalars(visible)) == {a, b}
    with platform_session(
        "tenant_directory", actor_user_id=None, request_id="tests-rls-tn-directory"
    ) as session:
        assert set(session.scalars(visible)) == {a, b, c}


def test_rls_tm_user_policy(committed_db: TestDatabase, keyring: KeyRing) -> None:
    a, b = (tenant_id_of(tenant_factory(keyring=keyring)) for _ in range(2))
    with identity_session(request_id="tests-rls-tm-user") as session:
        user_id = insert_app_user(session)
    for tenant_id in (a, b):
        with tenant_session(_all_entities(tenant_id)) as session:
            row = membership_row(RowContext(tenant_id, user_id), status=MembershipStatus.ACTIVE)
            session.execute(insert(tenant_membership).values(**row))

    # Each provisioned tenant also holds its admin membership, which the user policy hides.
    with identity_session(request_id="tests-rls-tm-member", user_id=user_id) as session:
        rows = session.execute(
            select(tenant_membership.c.tenant_id, tenant_membership.c.user_id)
        ).all()
    assert sorted(tuple(row) for row in rows) == sorted([(a, user_id), (b, user_id)])


def test_rls_tm_in_a_tenant_transaction_of_a_user(
    committed_db: TestDatabase, keyring: KeyRing
) -> None:
    """04 §1.4 RLS-TM (rev 1.272; dev-guide DG-KRN-DB-12; item USERS-MEMBER-TENANT-1): what a
    tenant's transaction reads and locks in ``tenant_membership``. U belongs to A and to B under
    ONE membership id — a loaded sandbox keeps the ids of its source — and V to both under two.

    With U as its user, a SELECT in A that names no tenant returns U's membership of B beside
    the members of A, and a read by U's id two rows: the user policy holds in a tenant's
    transaction as it does in an identity one. ``of_session_tenant`` leaves A's rows. A lock and
    an UPDATE reach A alone without it — the row must pass the policies of UPDATE too, and the
    tenant policy is the only one — and so does every statement of a transaction without a user,
    as a job's is. V's membership of B is read from neither.

    That holds for the row a statement locks or writes, and for no other: a SELECT that joins
    the table and locks ANOTHER one (``FOR UPDATE OF``), and an UPDATE of another table that
    reads this one, read U's membership of B as an open SELECT does."""
    a, b = (tenant_id_of(tenant_factory(keyring=keyring)) for _ in range(2))
    with identity_session(request_id="tests-rls-tm-tenant") as session:
        u, v = insert_app_user(session), insert_app_user(session)
    shared = new_id()
    v_in_b = None
    for tenant_id in (a, b):
        with tenant_session(_all_entities(tenant_id)) as session:
            row = membership_row(RowContext(tenant_id, u), status=MembershipStatus.ACTIVE)
            other = membership_row(RowContext(tenant_id, v), status=MembershipStatus.ACTIVE)
            session.execute(insert(tenant_membership).values(**(row | {"id": shared})))
            session.execute(insert(tenant_membership).values(**other))
            v_in_b = other["id"]

    table = tenant_membership
    people = table.c.user_id.in_((u, v))
    where = {"A": a, "B": b}
    who = {u: "U", v: "V"}

    def seen(session: Session, statement: Executable) -> list[str]:
        """``<tenant>:<user>`` of each row the statement returns, sorted."""
        return sorted(
            f"{next(name for name, tenant_id in where.items() if tenant_id == row.tenant_id)}"
            f":{who[row.user_id]}"
            for row in session.execute(statement)
        )

    columns = (table.c.tenant_id, table.c.user_id)
    by_id = select(*columns).where(table.c.id == shared)
    facts: dict[str, dict[str, list[str]]] = {}
    for label, user_id in (("U", u), ("no user", None)):
        with tenant_session(DbContext(tenant_id=a, user_id=user_id, entity_scope="*")) as session:
            facts[label] = {
                "no tenant named": seen(session, select(*columns).where(people)),
                "no tenant named, by id": seen(session, by_id),
                "of_session_tenant": seen(
                    session, select(*columns).where(of_session_tenant(table), people)
                ),
                "of_session_tenant, by id": seen(session, by_id.where(of_session_tenant(table))),
                "FOR UPDATE by id": seen(session, by_id.with_for_update()),
                "FOR SHARE by id": seen(session, by_id.with_for_update(read=True)),
                "UPDATE by id": seen(
                    session,
                    update(table)
                    .where(table.c.id == shared)
                    .values(last_opened_at=func.now())
                    .returning(*columns),
                ),
                "V's membership of B": seen(session, select(*columns).where(table.c.id == v_in_b)),
                "FOR UPDATE OF another table, by id": seen(
                    session,
                    select(*columns)
                    .join(app_user, app_user.c.id == table.c.user_id)
                    .where(table.c.id == shared)
                    .with_for_update(of=app_user),
                ),
                "UPDATE of another table by the membership of B": [
                    who[row.id]
                    for row in session.execute(
                        update(app_user)
                        .where(
                            app_user.c.id == table.c.user_id,
                            table.c.id == shared,
                            table.c.tenant_id == b,
                        )
                        .values(display_name=app_user.c.display_name)
                        .returning(app_user.c.id)
                    )
                ],
            }
            session.rollback()
    in_a, u_in_a = ["A:U", "A:V"], ["A:U"]
    tenant_alone = {
        "of_session_tenant": in_a,
        "of_session_tenant, by id": u_in_a,
        "FOR UPDATE by id": u_in_a,
        "FOR SHARE by id": u_in_a,
        "UPDATE by id": u_in_a,
        "V's membership of B": [],
    }
    assert facts == {
        "U": tenant_alone
        | {
            "no tenant named": ["A:U", "A:V", "B:U"],
            "no tenant named, by id": ["A:U", "B:U"],
            "FOR UPDATE OF another table, by id": ["A:U", "B:U"],
            "UPDATE of another table by the membership of B": ["U"],
        },
        "no user": tenant_alone
        | {
            "no tenant named": in_a,
            "no tenant named, by id": u_in_a,
            "FOR UPDATE OF another table, by id": u_in_a,
            "UPDATE of another table by the membership of B": [],
        },
    }
