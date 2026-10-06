"""The snapshot registry's deferred references against the INSTALLED database (D-98 140-A3 F1;
lane FIX-D1, supervisor ruling 2026-09-30: "a guard that under-reports is how this shipped").

A deferred reference is restored by the load's fixup step: the row is inserted with NULL and
UPDATEd by identity once the referenced table is in (05 SBX-04). That UPDATE runs as the
application role under every live guard, so a column the database freezes can never be deferred.
The CPU guard (``tests/unit/test_snapshot_dataset.py``) decides "frozen" from the 04 immutability
class; this module decides it from what the migrations INSTALLED — the application role's column
privileges, the row-level UPDATE triggers of each table and the class marker DB-14 (g) reads —
and ties the two together: the classes the CPU guard reads from 04 are the classes installed.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from erev_api.db.migration_ops import CONFIG_MUTABLE_COLUMNS
from erev_api.db.session import APP_ROLE, DbContext, identity_session, tenant_session
from erev_api.db.tables import metadata
from erev_api.db.transitions import TRANSITIONS
from erev_api.domain.platform import snapshot_dataset as sd
from sqlalchemy import exc, text, update
from sqlalchemy.orm import Session
from support.db import TestDatabase
from support.snapshots import immutability_classes

pytestmark = pytest.mark.pg

INSUFFICIENT_PRIVILEGE = "42501"
# The installed reasons a fixup UPDATE of a column is refused.
NO_GRANT = "the application role holds no UPDATE privilege on the column (42501)"
DB_01 = "DB-01: the row trigger forbids every UPDATE"
DB_03 = "DB-03: the transition trigger does not keep the column updatable in every status"
DB_04 = "DB-04: the column is frozen once the version has left DRAFT / TESTED"
DB_04_CHILD = "DB-04: the child row is frozen once its parent version has left DRAFT"
# D-98 140-A3 F1: the frozen deferrals still open — exact, so a NEW one is red and an entry that
# no longer violates must be removed. NONE is open: lane FIX-D1 closed the approval references by
# LOAD_ORDER and the self-references by referenced-first insertion, and slice 2 (supervisor
# ruling R-43 (b)) the last two by the row-ordered ``stream`` component.
KNOWN_FROZEN: dict[tuple[str, str], str] = {}
# The frozen edges the registry DID defer before lane FIX-D1 (main 5c3dbcc9; 21 of its 43 deferred
# edges) — the defect that shipped: each was a fixup UPDATE the installed database refuses, and
# the guard of the day (DB-03 kernel specs only) saw six of them. They now arrive WITH their row —
# an approval reference because the approval graphs load first (LOAD_ORDER), a self-reference
# because the dataset is inserted referenced-first, the two stream edges because their component
# loads in one row order. Pinned so the guard's verdict means something: its own function still
# judges every one of them frozen.
ONCE_DEFERRED_FROZEN: dict[tuple[str, str], str] = {
    ("contract_event", "estimate_version_id"): NO_GRANT,
    ("contract_event", "manual_adjustment_id"): NO_GRANT,
    ("pob_template_version", "supersedes_version_id"): DB_04,
    ("sod_rule", "supersedes_version_id"): DB_04,
    ("rule_set_version", "supersedes_version_id"): DB_04,
    ("account_mapping_version", "supersedes_version_id"): DB_04,
    ("registry_version", "supersedes_version_id"): DB_04,
    ("import_mapping_profile", "supersedes_version_id"): DB_04,
    ("fx_rate_set_version", "supersedes_version_id"): DB_04,
    ("ssp_book_version", "supersedes_version_id"): DB_04,
    ("sod_exception", "approval_request_id"): NO_GRANT,
    ("role_assignment", "approval_request_id"): NO_GRANT,
    ("contract_event", "approval_request_id"): NO_GRANT,
    ("contract_event", "supersedes_event_id"): NO_GRANT,
    ("import_row", "aggregated_into_row_id"): NO_GRANT,
    ("obligation", "parent_obligation_id"): NO_GRANT,
    ("obligation", "regrouped_from_obligation_id"): NO_GRANT,
    ("policy_override", "supersedes_id"): NO_GRANT,
    ("contract", "renewal_of_contract_id"): DB_03,
    ("judgement_record", "supersedes_id"): DB_03,
    ("estimate_version", "supersedes_version_id"): DB_03,
}

# pg_trigger.tgtype bits: 1 FOR EACH ROW, 16 UPDATE.
_UPDATE_TRIGGERS = text(
    "SELECT c.relname, t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'erev' AND NOT t.tgisinternal "
    "AND (t.tgtype & 1) <> 0 AND (t.tgtype & 16) <> 0"
)
_CLASS_MARKERS = text(
    "SELECT c.relname, obj_description(c.oid, 'pg_class') FROM pg_class c "
    "JOIN pg_namespace n ON n.oid = c.relnamespace "
    "WHERE n.nspname = 'erev' AND c.relkind IN ('r', 'p')"
)
_MAY_UPDATE = text(
    "SELECT has_column_privilege(:role, CAST(:table AS regclass), :column, 'UPDATE')"
)


def _deferred() -> list[tuple[str, str]]:
    """Every (COPIED dataset, deferred column) of the registry, in load order."""
    return [
        (dataset.name, column)
        for dataset in sd.inventory().datasets
        if dataset.snapshot_class is sd.SnapshotClass.COPIED
        for column in dataset.deferred
    ]


def _update_triggers(session: Session) -> dict[str, set[str]]:
    """Table → the purposes of its installed row-level UPDATE triggers (NC-16
    ``tg_<table>__<purpose>``): ``immutable``, ``transition``, ``config_version``,
    ``config_child``, ``touch`` and the table's own guards."""
    found: dict[str, set[str]] = {}
    for table, name in session.execute(_UPDATE_TRIGGERS):
        found.setdefault(str(table), set()).add(str(name).removeprefix(f"tg_{table}__"))
    return found


def _frozen_by(session: Session, table: str, column: str, triggers: set[str]) -> str | None:
    """Why the installed database refuses a fixup UPDATE of ``table.column`` on a row in its
    final state; None when it admits one."""
    may_update = session.execute(
        _MAY_UPDATE, {"role": APP_ROLE, "table": f"erev.{table}", "column": column}
    ).scalar_one()
    if not may_update:
        return NO_GRANT
    if "immutable" in triggers:
        return DB_01
    if "config_child" in triggers:
        return DB_04_CHILD
    if "config_version" in triggers and column not in CONFIG_MUTABLE_COLUMNS:
        return DB_04
    if "transition" in triggers:
        spec = TRANSITIONS[table]  # the installed body is this spec (test_transitions_drift.py)
        if column not in spec.updatable_columns or spec.frozen_while or spec.parent is not None:
            return DB_03
    return None


def test_no_deferred_reference_is_frozen_by_the_installed_database(
    test_database: TestDatabase,
) -> None:
    """Every deferred column of every COPIED dataset, judged by the installed privileges and
    triggers: the fixup UPDATE is admitted for all of them but the named set (empty since slice
    2). The registry defers exactly the columns listed, so the verdict is not vacuous."""
    deferred = _deferred()
    assert deferred == [
        ("pob_template_version", "approval_request_id"),
        ("sod_rule", "approval_request_id"),
        ("rule_set_version", "approval_request_id"),
        ("ssp_calculator_run", "draft_ssp_book_version_id"),
        ("combination_group", "judgement_record_id"),
        ("modification", "applied_event_id"),
        ("manual_adjustment", "applied_event_id"),  # the stream component's updatable back-edge
    ]
    with identity_session(request_id="tests-installed-freeze") as session:
        triggers = _update_triggers(session)
        frozen = {
            (table, column): reason
            for table, column in deferred
            if (reason := _frozen_by(session, table, column, triggers.get(table, set())))
            is not None
        }
        # what decides each admitted one, by the installed triggers of its table
        assert "config_version" in triggers["pob_template_version"]  # IM-P lifecycle column
        assert "config_version" in triggers["sod_rule"]
        assert "config_version" in triggers["rule_set_version"]
        for table in ("ssp_calculator_run", "combination_group", "modification"):
            assert "transition" in triggers[table], table  # DB-03 keeps the column updatable
        assert "transition" in triggers["manual_adjustment"]
    assert frozen == KNOWN_FROZEN


def test_the_frozen_edges_once_deferred_arrive_with_their_rows(
    test_database: TestDatabase,
) -> None:
    """The guard can fail, and the ordering fix is what it demanded: every edge of
    ``ONCE_DEFERRED_FROZEN`` is still judged frozen by the installed database, is no longer
    deferred, and reaches the sandbox with its row — as a self-reference inserted
    referenced-first, as a row reference of its component (one row order across its tables), or
    as a reference to a table that loads earlier."""
    inventory = sd.inventory()
    deferred = set(_deferred())
    position = {name: index for index, name in enumerate(sd.LOAD_ORDER)}
    targets = {(r.table, r.column): r.target for r in inventory.references}
    with identity_session(request_id="tests-once-deferred") as session:
        triggers = _update_triggers(session)
        for (table, column), reason in ONCE_DEFERRED_FROZEN.items():
            assert (table, column) not in deferred, (table, column)
            found = _frozen_by(session, table, column, triggers.get(table, set()))
            assert found == reason, (table, column)
            dataset = inventory.dataset(table)
            if targets[(table, column)] == table:
                assert column in dataset.self_references, (table, column)
            elif column in dataset.row_references:
                component = sd.COMPONENTS["contract_event"]
                assert {table, targets[(table, column)]} <= set(component.tables), (table, column)
            else:
                assert position[targets[(table, column)]] < position[table], (table, column)
    assert not set(ONCE_DEFERRED_FROZEN) & set(KNOWN_FROZEN)
    assert len(ONCE_DEFERRED_FROZEN) == 21


def test_the_fixup_statement_is_admitted_or_refused_by_privilege_as_the_guard_says(
    test_database: TestDatabase,
) -> None:
    """The guard's privilege verdict, behaviourally: the statement the fixup step issues — an
    UPDATE of one reference column by identity — is planned under a tenant session for every
    deferred column and for every once-deferred edge. It touches no row (``WHERE false``);
    PostgreSQL checks the column privilege all the same. Every deferred column is admitted;
    exactly the once-deferred edges the guard judges ``NO_GRANT`` are refused 42501."""
    context = DbContext(tenant_id=UUID(int=0xF1D1), user_id=None, entity_scope="*")
    refused: set[tuple[str, str]] = set()
    planned = [*_deferred(), *ONCE_DEFERRED_FROZEN]
    for table_name, column in planned:
        table = metadata.tables[f"erev.{table_name}"]
        statement = update(table).where(text("false")).values({column: None})
        try:
            with tenant_session(context) as session:
                session.execute(statement)
        except exc.DBAPIError as error:
            assert getattr(error.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE, error
            refused.add((table_name, column))
    assert not refused & set(_deferred())
    assert refused == {key for key, reason in ONCE_DEFERRED_FROZEN.items() if reason == NO_GRANT}
    assert len(refused) == 10


def test_the_classes_the_cpu_guard_reads_are_the_classes_installed(
    test_database: TestDatabase,
) -> None:
    """The CPU guard derives "frozen" from the 04 ``Class.`` line of each table; the installed
    marker (the table comment ``apply_class`` writes, read by DB-14 (g)) is the same class for
    every LOAD_ORDER table — an ``IM-P child`` is installed as IM-P with the DB-04 child trigger —
    and each class carries the trigger that enforces it."""
    documented = immutability_classes()
    assert set(documented) == set(sd.LOAD_ORDER)
    with identity_session(request_id="tests-installed-classes") as session:
        markers = {str(table): marker for table, marker in session.execute(_CLASS_MARKERS)}
        triggers = _update_triggers(session)
    for name, klass in sorted(documented.items()):
        assert markers[name] == klass.removesuffix(" child"), name
        purposes = triggers.get(name, set())
        if klass == "IM-P child":
            assert "config_child" in purposes, name
        elif klass == "IM-P":
            assert "config_version" in purposes, name
        elif klass == "IM-S":
            assert "transition" in purposes and name in TRANSITIONS, name
