"""T-PLT-47 ``registry_parameter_correction`` and the T-PLT-31 rule 3 effective relation (04 rev
1.59; dev-guide 1.53; D-98 candidate 125; Codex 0226 / 0408). CPU-only: the 0066 literals are
compared with the Python catalogue (the seed drift oracle), the downgrade is replayed against a
recording ``execute``, and the readers are checked to bind the effective relation, not the seed
table."""

from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path
from types import ModuleType

import sqlalchemy as sa
from erev_api.api.v1 import policies as policies_api
from erev_api.db.tables.platform import registry_parameter, registry_parameter_correction
from erev_api.domain.policies import registry_versions
from erev_api.registry import effective
from erev_api.registry.platform import PLATFORM_PARAMETERS
from sqlalchemy.dialects import postgresql

VERSIONS = Path(__file__).resolve().parents[2] / "erev_api/db/migrations/versions"
REVISION = VERSIONS / "0066_registry_parameter_correction.py"


def _module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"rev_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0066_sits_on_0065_and_its_literals_equal_the_python_catalogue() -> None:
    module = _module(REVISION)
    assert (module.revision, module.down_revision) == ("0066", "0065")
    spec = PLATFORM_PARAMETERS[module.CODE]
    assert module.CODE == "platform.snapshot_retention_families"
    # the seed drift oracle (DG-MIG-07): the appended row is the catalogue's rendering
    assert json.loads(module.VALUE_SCHEMA) == spec.value_schema
    assert json.loads(module.VALUE_SCHEMA)["anyOf"][0] == {"const": {}}  # 04 rev 1.56
    assert module.DESCRIPTION == spec.description
    assert module.SOURCE_REF == spec.source_ref
    assert module.SECTION == spec.section
    assert module.CORRECTION == (
        module.CODE,
        1,
        module.VALUE_SCHEMA,
        module.DESCRIPTION,
        module.SOURCE_REF,
        module.SECTION,
        "0066",
        "SYSTEM",
    )
    assert module.COLUMNS == (
        "code",
        "correction_no",
        "value_schema",
        "description",
        "source_ref",
        "section",
        "applied_by_revision",
        "created_by_kind",
    )


def test_0066_upgrade_appends_and_downgrade_drops_only_its_table() -> None:
    """Replayed through ``migration_ops.recording()`` (DG-ARC-09's twin): the upgrade creates the
    table, its class and grants and appends exactly one row; the downgrade drops only that table;
    the seeded ``registry_parameter`` is never written."""
    module = _module(REVISION)
    with module.ops.recording() as executed:
        module.downgrade()
    assert executed == ["DROP TABLE erev.registry_parameter_correction"]
    with module.ops.recording() as executed:
        module.upgrade()
    creates = [s for s in executed if s.lstrip().upper().startswith("CREATE TABLE")]
    assert len(creates) == 1 and "erev.registry_parameter_correction" in creates[0]
    inserts = [s for s in executed if s.lstrip().upper().startswith("INSERT INTO")]
    assert len(inserts) == 1 and inserts[0].startswith(
        "INSERT INTO erev.registry_parameter_correction"
    )
    assert "platform.snapshot_retention_families" in inserts[0] and "'0066'" in inserts[0]
    assert any("fk_registry_parameter_correction__code" in s for s in executed)  # FK to the seed
    assert any("IS 'IM-A'" in s for s in executed)  # DB-14 (g) class marker
    assert any("GRANT SELECT ON TABLE erev.registry_parameter_correction" in s for s in executed)
    assert not any("GRANT" in s and "INSERT" in s for s in executed)  # erev_app reads only
    # the seed table is referenced by the foreign key and never written
    written = [
        s
        for s in executed
        if s.lstrip().upper().startswith(("UPDATE ", "DELETE ", "INSERT INTO"))
        and "erev.registry_parameter " in s + " "
    ]
    assert written == []


def test_orm_table_follows_t_plt_47() -> None:
    assert list(registry_parameter_correction.c.keys()) == [
        "code",
        "correction_no",
        "value_schema",
        "description",
        "source_ref",
        "section",
        "applied_by_revision",
        "created_at",
        "created_by",
        "created_by_kind",
    ]
    assert [c.name for c in registry_parameter_correction.primary_key.columns] == [
        "code",
        "correction_no",
    ]
    assert all(
        not registry_parameter_correction.c[name].nullable for name in effective.METADATA_COLUMNS
    )  # complete snapshots: every metadata column NOT NULL (04 T-PLT-47)
    fk = next(iter(registry_parameter_correction.c.code.foreign_keys))
    assert fk.column is registry_parameter.c.code


def test_effective_relation_reads_the_latest_correction_over_the_seed() -> None:
    sql = str(
        sa.select(effective.EFFECTIVE_REGISTRY_PARAMETER).compile(dialect=postgresql.dialect())
    )
    assert "DISTINCT ON (erev.registry_parameter_correction.code)" in sql
    assert (
        "ORDER BY erev.registry_parameter_correction.code, "
        "erev.registry_parameter_correction.correction_no DESC"
    ) in sql
    for name in effective.METADATA_COLUMNS:
        assert (
            f"coalesce(latest_correction.{name}, erev.registry_parameter.{name}) AS {name}" in sql
        )
    assert sql.count("coalesce(") == 4  # exactly the four metadata columns
    for behavioural in ("pin", "approval_code", "allowed_levels", "default_asc606", "category"):
        assert f"erev.registry_parameter.{behavioural} AS {behavioural}" in sql
        assert f"latest_correction.{behavioural}" not in sql
    assert "LEFT OUTER JOIN" in sql  # a code without corrections keeps its seed (fallback)
    assert set(effective.EFFECTIVE_REGISTRY_PARAMETER.c.keys()) == set(registry_parameter.c.keys())


def test_readers_bind_the_effective_relation_not_the_seed_table() -> None:
    spec = policies_api.PARAMETER_LIST
    relation = effective.EFFECTIVE_REGISTRY_PARAMETER
    columns = [
        *spec.sort_keys.values(),
        *(f.column for f in spec.filters.values()),
        *spec.search_columns,
    ]
    assert columns and all(column.table is relation for column in columns)
    source = inspect.getsource(registry_versions.list_parameters)
    assert "EFFECTIVE_REGISTRY_PARAMETER" in source and "select(registry_parameter)" not in source
