"""Migration helper SQL and revision files (dev-guide §6.5, §4.2; BUILD_SPEC FND-6)."""

from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

import pytest
import sqlalchemy as sa
from erev_api.db import migration_ops as ops

ROOT = Path(__file__).resolve().parents[3]


def test_dg_mig_06_remove_enum_value_sql() -> None:
    statements = ops.remove_enum_value_sql(
        "probe_kind",
        ["ALPHA", "GAMMA"],
        [
            ops.EnumColumn(table="probe_one", column="kind"),
            ops.EnumColumn(table="probe_two", column="kinds", is_array=True),
            ops.EnumColumn(table="probe_three", column="kind", default="'ALPHA'::erev.probe_kind"),
        ],
    )
    assert statements == [
        "ALTER TYPE erev.probe_kind RENAME TO probe_kind__old",
        "CREATE TYPE erev.probe_kind AS ENUM ('ALPHA', 'GAMMA')",
        "ALTER TABLE erev.probe_one ALTER COLUMN kind TYPE erev.probe_kind "
        "USING kind::text::erev.probe_kind",
        "ALTER TABLE erev.probe_two ALTER COLUMN kinds TYPE erev.probe_kind[] "
        "USING kinds::text[]::erev.probe_kind[]",
        "ALTER TABLE erev.probe_three ALTER COLUMN kind DROP DEFAULT",
        "ALTER TABLE erev.probe_three ALTER COLUMN kind TYPE erev.probe_kind "
        "USING kind::text::erev.probe_kind",
        "ALTER TABLE erev.probe_three ALTER COLUMN kind SET DEFAULT 'ALPHA'::erev.probe_kind",
        "DROP TYPE erev.probe_kind__old",
    ]


def test_dg_mig_06_remove_enum_value_sql_carries_dependents() -> None:
    """DG-MIG-06 (dev-guide rev 1.171): a check constraint and an index whose stored expression
    holds a constant of the type are dropped before the type is replaced and re-created from
    their catalogue definitions after the old type is gone — in that order."""
    check = "CHECK ((kind = ANY (ARRAY['ALPHA'::probe_kind, 'GAMMA'::probe_kind])))"
    index = (
        "CREATE UNIQUE INDEX ux_probe_one__alpha ON erev.probe_one USING btree (id) "
        "WHERE (kind = 'ALPHA'::probe_kind)"
    )
    statements = ops.remove_enum_value_sql(
        "probe_kind",
        ["ALPHA", "GAMMA"],
        [ops.EnumColumn(table="probe_one", column="kind")],
        [
            ops.EnumDependent(table="probe_one", name="ck_probe_one__kind", definition=check),
            ops.EnumDependent(
                table="probe_one", name="ux_probe_one__alpha", definition=index, is_index=True
            ),
        ],
    )
    assert statements == [
        "ALTER TABLE erev.probe_one DROP CONSTRAINT ck_probe_one__kind",
        "DROP INDEX erev.ux_probe_one__alpha",
        "ALTER TYPE erev.probe_kind RENAME TO probe_kind__old",
        "CREATE TYPE erev.probe_kind AS ENUM ('ALPHA', 'GAMMA')",
        "ALTER TABLE erev.probe_one ALTER COLUMN kind TYPE erev.probe_kind "
        "USING kind::text::erev.probe_kind",
        "DROP TYPE erev.probe_kind__old",
        f"ALTER TABLE erev.probe_one ADD CONSTRAINT ck_probe_one__kind {check}",
        index,
    ]


def test_create_monthly_partitions_window() -> None:
    with ops.recording() as statements:
        ops.create_monthly_partitions("audit_event")
    names = [statement.split()[2] for statement in statements]
    monthly = [name for name in names if name != "erev.audit_event_pdefault"]
    assert len(monthly) == 180
    assert monthly[0] == "erev.audit_event_p201801"
    assert monthly[-1] == "erev.audit_event_p203212"
    assert names[-1] == "erev.audit_event_pdefault"
    assert len(set(names)) == 181
    assert statements[0].endswith(
        "PARTITION OF erev.audit_event FOR VALUES "
        "FROM ('2018-01-01 00:00:00+00') TO ('2018-02-01 00:00:00+00')"
    )
    assert statements[179].endswith("FROM ('2032-12-01 00:00:00+00') TO ('2033-01-01 00:00:00+00')")
    assert statements[-1] == (
        "CREATE TABLE erev.audit_event_pdefault PARTITION OF erev.audit_event DEFAULT"
    )
    with ops.recording() as dated:
        ops.create_monthly_partitions("schedule_line", first="2024-11", last="2025-01")
    assert dated[1].endswith("FROM ('2024-12-01') TO ('2025-01-01')")
    with pytest.raises(ValueError, match="not a partitioned table"):
        ops.monthly_partition_statements("contract_event")


def test_dg_mig_02_revision_renderer() -> None:
    source = ops.render_revision(number="0042", slug="probe", item="FND-6", down_revision="0041")
    module = ast.parse(source)
    docstring = ast.get_docstring(module)
    assert docstring is not None and docstring.startswith("BUILD_SPEC item FND-6")
    assigned = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }
    assert assigned["revision"] == "0042"
    assert assigned["down_revision"] == "0041"
    with pytest.raises(ValueError):
        ops.render_revision(number="42", slug="probe", item="FND-6", down_revision=None)


def test_dg_mk_revision_writes_after_the_head(tmp_path: Path) -> None:
    first = tmp_path / "0001_schema_foundation.py"
    first.write_text(ops.render_revision(number="0001", slug="a", item="FND-6", down_revision=None))
    written = ops.write_revision("Global catalogues!", "FND-7", versions_dir=tmp_path)
    assert written.name == "0002_global_catalogues.py"
    assert "down_revision = '0001'" in written.read_text()


def test_im_p_child_without_sc_m_takes_no_touch_trigger() -> None:
    assert ops.class_statements("probe", "IM-P", without_sc_m=True) == [
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE erev.probe TO erev_app",
        "COMMENT ON TABLE erev.probe IS 'IM-P'",
    ]
    assert any(
        "erev.tg_touch()" in statement for statement in ops.class_statements("probe", "IM-P")
    )
    with pytest.raises(ValueError, match="without_sc_m"):
        ops.class_statements("probe", "IM-M", without_sc_m=True)


def test_config_child_trigger_arguments() -> None:
    with ops.recording() as fixed:
        ops.add_config_child_trigger(
            "rule", parent_table="rule_set_version", parent_column="rule_set_version_id"
        )
    assert fixed == [
        "CREATE TRIGGER tg_rule__config_child BEFORE INSERT OR UPDATE OR DELETE ON erev.rule "
        "FOR EACH ROW EXECUTE FUNCTION erev.tg_config_child('rule_set_version', "
        "'rule_set_version_id')"
    ]
    with ops.recording() as polymorphic:
        ops.add_config_child_trigger(
            "rule_test_case", parent_table=None, parent_column="subject_id"
        )
    assert polymorphic[0].endswith("erev.tg_config_child('*', 'subject_id')")


def test_class_statements_follow_04_1_5() -> None:
    im_a = ops.class_statements("probe", "IM-A")
    assert im_a[0] == "GRANT SELECT, INSERT ON TABLE erev.probe TO erev_app"
    assert "BEFORE UPDATE OR DELETE ON erev.probe FOR EACH ROW" in im_a[1]
    assert "BEFORE TRUNCATE ON erev.probe FOR EACH STATEMENT" in im_a[2]
    assert im_a[-1] == "COMMENT ON TABLE erev.probe IS 'IM-A'"
    im_s = ops.class_statements("probe", "IM-S", update_columns=["status"])
    assert im_s[:2] == [
        "GRANT SELECT, INSERT ON TABLE erev.probe TO erev_app",
        "GRANT UPDATE (status) ON TABLE erev.probe TO erev_app",
    ]
    assert "BEFORE DELETE ON erev.probe" in im_s[2]
    # 04 T-PLT-29: an IM-A table with an update allow-list leaves UPDATE to its DB-03 trigger.
    im_a_allow = ops.class_statements("probe", "IM-A", update_columns=["legal_hold"])
    assert im_a_allow[:2] == [
        "GRANT SELECT, INSERT ON TABLE erev.probe TO erev_app",
        "GRANT UPDATE (legal_hold) ON TABLE erev.probe TO erev_app",
    ]
    assert "BEFORE DELETE ON erev.probe FOR EACH ROW" in im_a_allow[2]
    assert "BEFORE TRUNCATE ON erev.probe FOR EACH STATEMENT" in im_a_allow[3]
    assert im_a_allow[-1] == "COMMENT ON TABLE erev.probe IS 'IM-A'"
    im_m = ops.class_statements("probe", "IM-M", delete_allowed=True)
    assert im_m[0] == "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE erev.probe TO erev_app"
    assert "EXECUTE FUNCTION erev.tg_touch()" in im_m[1]
    with pytest.raises(ValueError):
        ops.class_statements("probe", "IM-S")
    with pytest.raises(ValueError):
        ops.class_statements("probe", "IM-A", delete_allowed=True)
    with pytest.raises(ValueError):
        ops.class_statements("Probe; DROP", "IM-A")


def test_global_reference_grants_select_only() -> None:
    statements = ops.class_statements("probe", "IM-A", global_reference=True)
    assert statements[0] == "GRANT SELECT ON TABLE erev.probe TO erev_app"
    assert "BEFORE UPDATE OR DELETE ON erev.probe FOR EACH ROW" in statements[1]
    assert statements[-1] == "COMMENT ON TABLE erev.probe IS 'IM-A'"
    with pytest.raises(ValueError):
        ops.class_statements("probe", "IM-M", global_reference=True)


def test_select_only_identity_table_grants() -> None:
    statements = ops.class_statements("probe", "IM-M", select_only=True)
    assert statements[0] == "GRANT SELECT ON TABLE erev.probe TO erev_app"
    assert "EXECUTE FUNCTION erev.tg_touch()" in statements[1]
    with pytest.raises(ValueError):
        ops.class_statements("probe", "IM-A", select_only=True)
    with pytest.raises(ValueError):
        ops.class_statements("probe", "IM-M", select_only=True, update_columns=["status"])


def test_update_forbidden_mutable_table() -> None:
    statements = ops.class_statements("probe", "IM-M", delete_allowed=True, update_forbidden=True)
    assert statements[0] == "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE erev.probe TO erev_app"
    assert statements[1] == (
        "CREATE TRIGGER tg_probe__immutable BEFORE UPDATE ON erev.probe "
        "FOR EACH ROW EXECUTE FUNCTION erev.tg_forbid_mutation()"
    )
    assert not [statement for statement in statements if "tg_touch" in statement]
    assert statements[-1] == "COMMENT ON TABLE erev.probe IS 'IM-M'"
    with pytest.raises(ValueError):
        ops.class_statements("probe", "IM-S", update_columns=["status"], update_forbidden=True)
    with pytest.raises(ValueError):
        ops.class_statements("probe", "IM-M", select_only=True, update_forbidden=True)


def test_global_table_standard_sets_checks_indexes_and_foreign_keys() -> None:
    with ops.recording() as statements:
        ops.create_global_table(
            "probe",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=True),
            primary_key=["id"],
            standard_sets=["SC-C"],
            checks=[("ck_probe__user", "user_id IS NOT NULL")],
            indexes=[("ix_probe__user_id", ["user_id"], None)],
        )
        ops.add_global_fk("probe", "user_id", "app_user")
        ops.create_indexes(
            "probe", [("ux_probe__user", ["user_id"], None)], unique=True, tenant_leading=False
        )
    assert "created_by_kind erev.principal_kind NOT NULL" in statements[0]
    assert "CONSTRAINT ck_probe__user CHECK (user_id IS NOT NULL)" in statements[0]
    assert statements[2] == "CREATE INDEX ix_probe__user_id ON erev.probe (user_id)"
    assert statements[3] == (
        "ALTER TABLE erev.probe ADD CONSTRAINT fk_probe__user FOREIGN KEY (user_id) "
        "REFERENCES erev.app_user (id) ON DELETE RESTRICT ON UPDATE RESTRICT"
    )
    assert statements[4] == "CREATE UNIQUE INDEX ux_probe__user ON erev.probe (user_id)"
    with pytest.raises(ValueError), ops.recording():
        ops.create_global_table(
            "probe",
            sa.Column("id", sa.Uuid(), nullable=False),
            primary_key=["id"],
            checks=[("probe_user", "id IS NOT NULL")],
        )
    with pytest.raises(ValueError), ops.recording():
        ops.create_global_table(
            "probe",
            sa.Column("id", sa.Uuid(), nullable=False),
            primary_key=["id"],
            standard_sets=["SC-V"],
        )


def test_tenant_table_without_sc_t_id() -> None:
    with ops.recording() as statements:
        ops.create_tenant_table(
            "probe",
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("id", sa.Uuid(), nullable=False),
            include_id=False,
            partition_by="occurred_at",
            primary_key=["tenant_id", "occurred_at", "id"],
        )
    assert statements[0].startswith(
        "CREATE TABLE erev.probe (\n\ttenant_id UUID NOT NULL, \n\toccurred_at TIMESTAMP WITH TIME "
        "ZONE NOT NULL, \n\tid UUID NOT NULL"
    )
    assert "PRIMARY KEY (tenant_id, occurred_at, id)" in statements[0]
    assert statements[0].endswith("PARTITION BY RANGE (occurred_at)")
    with pytest.raises(ValueError, match="names its primary key"), ops.recording():
        ops.create_tenant_table("probe", include_id=False)


def test_global_table_unique_index_and_enum_drop() -> None:
    with ops.recording() as statements:
        ops.create_global_table(
            "probe",
            sa.Column("code", sa.Text(), nullable=False),
            sa.Column("pol_id", sa.Text(), nullable=True),
            primary_key=["code"],
            unique=[("ux_probe__pol_id", ["pol_id"], "pol_id IS NOT NULL")],
        )
        ops.drop_enum("probe_kind")
    assert statements[1] == "REVOKE ALL ON TABLE erev.probe FROM PUBLIC"
    assert statements[2] == (
        "CREATE UNIQUE INDEX ux_probe__pol_id ON erev.probe (pol_id) WHERE pol_id IS NOT NULL"
    )
    assert statements[3] == "DROP TYPE erev.probe_kind"
    with pytest.raises(ValueError), ops.recording():
        ops.create_global_table(
            "probe",
            sa.Column("code", sa.Text(), nullable=False),
            primary_key=["code"],
            unique=[("probe_code", ["code"], None)],
        )


def test_dg_mig_07_insert_rows_sql() -> None:
    statement = ops.insert_rows_sql(
        "probe", ("code", "name", "units", "is_active", "note"), [("TOP", "Pa'anga", 2, True, None)]
    )
    assert statement == (
        "INSERT INTO erev.probe (code, name, units, is_active, note) VALUES\n"
        "  ('TOP', 'Pa''anga', 2, TRUE, NULL)"
    )
    with pytest.raises(ValueError):
        ops.insert_rows_sql("probe", ("code",), [])
    with pytest.raises(ValueError):
        ops.insert_rows_sql("probe", ("code", "name"), [("TOP",)])
    with pytest.raises(TypeError):
        ops.insert_rows_sql("probe", ("rate",), [(1.5,)])  # type: ignore[list-item]
    with pytest.raises(ValueError):
        ops.insert_rows_sql("probe", ("code",), [("a\x00b",)])


def test_rls_templates_follow_04_1_4() -> None:
    te = ops.rls_statements("probe", "RLS-TE", entity_column="entity_id")
    assert te[:2] == [
        "ALTER TABLE erev.probe ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE erev.probe FORCE ROW LEVEL SECURITY",
    ]
    assert "pl_probe__tenant ON erev.probe FOR ALL TO erev_app" in te[2]
    assert "AS RESTRICTIVE" in te[3] and "erev.entity_in_scope(entity_id)" in te[3]
    with pytest.raises(ValueError):
        ops.rls_statements("probe", "RLS-T", entity_column="entity_id")
    # 04 T-PLT-17: a NULL entity is a tenant-wide row visible to every scope.
    nullable = ops.rls_statements(
        "probe", "RLS-TE", entity_column="entity_id", entity_nullable=True
    )
    assert "USING ((entity_id IS NULL OR (SELECT erev.entity_in_scope(entity_id))))" in nullable[3]
    assert nullable[:3] == te[:3]
    with pytest.raises(ValueError):
        ops.rls_statements("probe", "RLS-T", entity_nullable=True)


def test_dg_mk_db_reset_refuses_running_stack(tmp_path: Path) -> None:
    marker = tmp_path / "invoked"
    recorder = tmp_path / "recorder.sh"
    recorder.write_text(f'#!/bin/sh\necho "$0 $*" >> "{marker}"\n')
    recorder.chmod(0o755)
    (tmp_path / "api.pid").write_text(f"{os.getpid()}\n")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in ("MAKEFLAGS", "MAKELEVEL", "MFLAGS")
    }
    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "db-reset",
            f"RUN_DIR={tmp_path}",
            f"EREV={recorder}",
            f"ALEMBIC={recorder}",
            f"PY={recorder}",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    # The recipe exits 1; GNU make reports it as "Error 1" and itself exits 2 (SPEC-Q-23).
    assert result.returncode == 2
    assert "[db-reset] Error 1" in result.stderr
    assert "dev stack running; run make dev-down first" in result.stdout
    assert not marker.exists()
