"""Catalogue lint DB-14 (04 §14.1; dev-guide §9.4 DG-TST-24; BUILD_SPEC FND-6)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from erev_api.db import migration_ops as ops
from erev_api.db.lint import LintFinding, lint_as_app, run_lint
from sqlalchemy import Connection
from support.db import TestDatabase

pytestmark = pytest.mark.pg


@pytest.fixture
def owner_transaction(test_database: TestDatabase) -> Iterator[Connection]:
    """An owner transaction that always rolls back, so probe objects never persist."""
    with test_database.owner_engine.connect() as connection:
        connection.begin()
        try:
            yield connection
        finally:
            connection.rollback()


def _names(findings: list[LintFinding], check: str) -> set[str]:
    return {finding.object_name for finding in findings if finding.check == check}


def test_db_14_detects_table_without_forced_rls(owner_transaction: Connection) -> None:
    assert run_lint(owner_transaction) == []
    owner_transaction.exec_driver_sql("CREATE TABLE erev.lint_probe (tenant_id uuid)")
    findings = run_lint(owner_transaction)
    assert [(f.check, f.object_name) for f in findings] == [("a", "lint_probe")]
    assert "ROW LEVEL SECURITY, FORCE, a policy" in findings[0].message


def test_db_14_detects_security_definer_function(owner_transaction: Connection) -> None:
    owner_transaction.exec_driver_sql(
        "CREATE FUNCTION erev.lint_probe_definer() RETURNS integer LANGUAGE sql "
        "SECURITY DEFINER SET search_path = erev, pg_catalog AS 'SELECT 1'"
    )
    findings = run_lint(owner_transaction)
    assert _names(findings, "h") == {"erev.lint_probe_definer()"}


def test_db_14_detects_partition_without_truncate_trigger(owner_transaction: Connection) -> None:
    owner_transaction.exec_driver_sql(
        "CREATE TABLE erev.partition_probe (id uuid, occurred_at timestamptz) "
        "PARTITION BY RANGE (occurred_at)"
    )
    with ops.bound_to(owner_transaction):
        ops.apply_class("partition_probe", "IM-A")
        ops.create_monthly_partitions(
            "partition_probe", first="2026-09", last="2026-10", partition_column="occurred_at"
        )
    assert run_lint(owner_transaction, checks=("g",)) == []

    owner_transaction.exec_driver_sql(
        "DROP TRIGGER tg_partition_probe_p202609__truncate ON erev.partition_probe_p202609"
    )
    findings = run_lint(owner_transaction, checks=("g",))
    assert [(f.check, f.object_name) for f in findings] == [("g", "partition_probe_p202609")]
    assert "IM-A table partition_probe" in findings[0].message


def test_db_14_im_a_update_allow_list_through_transition_trigger(
    owner_transaction: Connection,
) -> None:
    # 04 T-PLT-29: an IM-A table whose updatable columns are allow-listed guards UPDATE with its
    # DB-03 transition trigger, and DELETE and TRUNCATE with DB-01.
    run = owner_transaction.exec_driver_sql
    run("CREATE TABLE erev.lint_probe_allow (tenant_id uuid, flag boolean)")
    run("COMMENT ON TABLE erev.lint_probe_allow IS 'IM-A'")
    run(
        "CREATE TRIGGER tg_lint_probe_allow__immutable BEFORE DELETE ON erev.lint_probe_allow "
        "FOR EACH ROW EXECUTE FUNCTION erev.tg_forbid_mutation()"
    )
    run(
        "CREATE TRIGGER tg_lint_probe_allow__truncate BEFORE TRUNCATE ON erev.lint_probe_allow "
        "FOR EACH STATEMENT EXECUTE FUNCTION erev.tg_forbid_mutation()"
    )
    assert _names(run_lint(owner_transaction, checks=("g",)), "g") == {"lint_probe_allow"}
    run(
        "CREATE FUNCTION erev.tg_lint_probe_allow__transition() RETURNS trigger "
        "LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$"
    )
    run(
        "CREATE TRIGGER tg_lint_probe_allow__transition BEFORE UPDATE ON erev.lint_probe_allow "
        "FOR EACH ROW EXECUTE FUNCTION erev.tg_lint_probe_allow__transition()"
    )
    assert _names(run_lint(owner_transaction, checks=("g",)), "g") == set()


def test_db_14_app_role_attributes(test_database: TestDatabase) -> None:
    assert lint_as_app(request_id="tests-lint-d", checks=("d",)) == []


def test_db_14_import_template_in_global_allow_list(owner_transaction: Connection) -> None:
    # 04 T-IMP-01 (BUILD_SPEC DIN-1): the global registry has no tenant_id, is allow-listed by (b),
    # carries the DB-01 triggers of IM-A (g), and erev_app reads it only.
    run = owner_transaction.exec_driver_sql
    assert run_lint(owner_transaction) == []
    columns = run(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'erev' AND table_name = 'import_template'"
    ).scalars()
    assert "tenant_id" not in set(columns)
    grants = run(
        "SELECT privilege_type FROM information_schema.role_table_grants "
        "WHERE table_schema = 'erev' AND table_name = 'import_template' AND grantee = 'erev_app'"
    ).scalars()
    assert sorted(grants) == ["SELECT"]
    assert run("SELECT count(*) FROM erev.import_template").scalar_one() == 19
    run("DROP TRIGGER tg_import_template__immutable ON erev.import_template")
    assert _names(run_lint(owner_transaction, checks=("b", "g")), "g") == {"import_template"}


def test_db_14_detects_global_view_partition_and_append_only_gaps(
    owner_transaction: Connection,
) -> None:
    run = owner_transaction.exec_driver_sql
    run("CREATE TABLE erev.lint_probe_global (code text PRIMARY KEY)")
    run("CREATE VIEW erev.v_lint_probe AS SELECT 1 AS x")
    run("CREATE TABLE erev.lint_probe_parent (tenant_id uuid, d date) PARTITION BY RANGE (d)")
    run("ALTER TABLE erev.lint_probe_parent ENABLE ROW LEVEL SECURITY")
    run("ALTER TABLE erev.lint_probe_parent FORCE ROW LEVEL SECURITY")
    run(
        "CREATE POLICY pl_lint_probe_parent__tenant ON erev.lint_probe_parent FOR ALL TO erev_app "
        "USING (tenant_id = (SELECT erev.current_tenant_id()))"
    )
    run(
        "CREATE TABLE erev.lint_probe_child PARTITION OF erev.lint_probe_parent "
        "FOR VALUES FROM ('2020-01-01') TO ('2020-02-01')"
    )
    run("GRANT SELECT ON erev.lint_probe_child TO erev_app")
    run("COMMENT ON TABLE erev.lint_probe_global IS 'IM-A'")
    findings = run_lint(owner_transaction)
    assert _names(findings, "b") == {"lint_probe_global"}
    assert _names(findings, "e") == {"v_lint_probe"}
    assert _names(findings, "f") == {"lint_probe_child"}
    assert _names(findings, "g") == {"lint_probe_global"}
    assert _names(findings, "a") == set()

    run(
        "CREATE TRIGGER tg_lint_probe_global__immutable BEFORE UPDATE OR DELETE "
        "ON erev.lint_probe_global FOR EACH ROW EXECUTE FUNCTION erev.tg_forbid_mutation()"
    )
    assert _names(run_lint(owner_transaction), "g") == {"lint_probe_global"}
    run(
        "CREATE TRIGGER tg_lint_probe_global__truncate BEFORE TRUNCATE "
        "ON erev.lint_probe_global FOR EACH STATEMENT EXECUTE FUNCTION erev.tg_forbid_mutation()"
    )
    assert _names(run_lint(owner_transaction), "g") == set()


def test_db_14_detects_a_partition_without_the_period_guard(
    owner_transaction: Connection,
) -> None:
    """Check (i) (04 §14.1 DB-07 and DB-14 rev 1.182; supervisor ruling R-97 (7), gap G1 of the
    independent review of revision 0084): the DB-07 guard reaches the partitions of
    ``subledger_line`` only through PostgreSQL's copy of the parent's row trigger. A monthly
    partition, the default partition or the unpartitioned ``journal_line`` whose guard is disabled
    is named; a parent whose trigger is dropped loses every partition's copy with it, and each
    relation of the tree is named. Until rev 1.182 the lint read the DB-01 triggers only and
    answered no finding for any of these."""
    run = owner_transaction.exec_driver_sql
    assert run_lint(owner_transaction, checks=("i",)) == []
    run("ALTER TABLE erev.subledger_line_p202601 DISABLE TRIGGER tg_subledger_line__period_guard")
    findings = run_lint(owner_transaction, checks=("i",))
    assert [(f.check, f.object_name) for f in findings] == [("i", "subledger_line_p202601")]
    assert "DB-07 period guard of subledger_line" in findings[0].message
    run("ALTER TABLE erev.subledger_line_pdefault DISABLE TRIGGER tg_subledger_line__period_guard")
    run("ALTER TABLE erev.journal_line DISABLE TRIGGER tg_journal_line__period_guard")
    assert _names(run_lint(owner_transaction, checks=("i",)), "i") == {
        "journal_line",
        "subledger_line_p202601",
        "subledger_line_pdefault",
    }
    # the whole run names them too, and nothing else of the migrated catalogue
    assert {(f.check, f.object_name) for f in run_lint(owner_transaction)} == {
        ("i", "journal_line"),
        ("i", "subledger_line_p202601"),
        ("i", "subledger_line_pdefault"),
    }
    # the parent's trigger dropped: its 180 monthly copies and the default partition's go with it
    run("DROP TRIGGER tg_subledger_line__period_guard ON erev.subledger_line")
    named = _names(run_lint(owner_transaction, checks=("i",)), "i")
    assert {"subledger_line", "subledger_line_p201801", "subledger_line_p203212"} <= named
    assert len(named) == 182 + 1  # the tree of subledger_line, and journal_line


def test_db_14_lint_clean(test_database: TestDatabase) -> None:
    # DG-TST-24 (CLO-1): the DB-14 lint of the migrated catalogue answers no finding.
    assert lint_as_app(request_id="tests-db-14-clean") == []
