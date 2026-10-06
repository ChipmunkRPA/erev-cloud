"""T-PLT-34 ``tenant_snapshot`` — revision 0062 on P2's 0061 (BUILD_SPEC SNP-1 slice I-1; 04
T-PLT-34, §14.1 DB-03, DB-15; lane record §13.1, §13.4.9). CPU-only: the revision module is imported
as a file, its constants compared with the registry rendering; the row builder covers every NOT NULL
column."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import UUID

import pytest
from erev_api.db.tables import metadata, tenant_snapshot
from erev_api.db.transitions import TRANSITIONS, transition_trigger_sql
from erev_api.domain.platform import snapshots
from erev_api.registry.platform import PLATFORM_PARAMETERS
from erev_api.registry.versions import schema_errors
from support.rows import ROW_BUILDERS, tenant_snapshot_values

REVISION = (
    Path(__file__).resolve().parents[2]
    / "erev_api/db/migrations/versions/0062_snp_1_tenant_snapshot.py"
)
RETENTION_REVISION = REVISION.with_name("0063_snp_1_retention_parameter.py")


def _revision_module(path: Path = REVISION) -> object:
    spec = importlib.util.spec_from_file_location(f"snp1_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_0062_sits_on_0061_and_its_bodies_match_the_registry() -> None:
    module = _revision_module()
    # the assigned id and parent (merge prep 2026-09-20; the provisional 0099 / 0054 are gone)
    assert (module.revision, module.down_revision) == ("0062", "0061")  # on P2's 0061
    assert "PROVISIONAL" not in (module.__doc__ or "")
    assert module.TRANSITION_BODY == transition_trigger_sql("tenant_snapshot")
    assert "EREV-SBX-001" in module.TARGET_BODY and "'sandbox'" in module.TARGET_BODY
    assert "unknown or hidden" in module.TARGET_BODY  # a target hidden by RLS is refused too
    assert set(module.UPDATE_COLUMNS) == {
        "status",
        *TRANSITIONS["tenant_snapshot"].updatable_columns,
    }
    assert module.PURPOSES == ("SANDBOX_COPY", "STORED_BACKUP", "SANDBOX_SEED")


def test_table_and_transitions_follow_t_plt_34() -> None:
    assert [c.name for c in tenant_snapshot.columns] == [
        "tenant_id",
        "id",
        "known_at",
        "purpose",
        "status",
        "target_tenant_id",
        "manifest_file_id",
        "manifest_sha256",
        "row_counts",
        "job_id",
        "started_at",
        "finished_at",
        "created_at",
        "created_by",
        "created_by_kind",
    ]
    assert "erev.tenant_snapshot" in metadata.tables
    spec = TRANSITIONS["tenant_snapshot"]
    assert spec.status_column == "status"
    assert spec.pairs == frozenset(
        {
            ("QUEUED", "RUNNING"),
            ("RUNNING", "SUCCEEDED"),
            ("RUNNING", "FAILED"),
            ("QUEUED", "FAILED"),
        }
    )
    assert spec.set_once == frozenset(
        {"manifest_file_id", "manifest_sha256", "started_at", "finished_at"}
    )
    assert "target_tenant_id" in spec.updatable_columns and "job_id" not in spec.updatable_columns


def test_row_builder_covers_every_not_null_column() -> None:
    values = tenant_snapshot_values(UUID(int=1))
    required = {
        c.name for c in tenant_snapshot.columns if not c.nullable and c.server_default is None
    }
    assert required <= set(values), required - set(values)
    assert values["status"] == "QUEUED" and values["purpose"] == "STORED_BACKUP"
    assert "tenant_snapshot" in ROW_BUILDERS


def test_retention_seed_downgrade_is_a_documented_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    """DG-MIG-04 append-only seed exception (dev-guide rev 1.48; found by the integrated DB gate
    batch on main 0cb36c14, EREV-IMM-001): ``registry_parameter`` is append-only, so 0063's
    ``downgrade()`` executes nothing and says why, and its ``upgrade()`` is one idempotent insert —
    never a DELETE."""
    module = _revision_module(RETENTION_REVISION)
    executed: list[str] = []
    monkeypatch.setattr(module.ops, "execute", lambda statement: executed.append(str(statement)))
    module.downgrade()
    assert executed == []
    reason = module.downgrade.__doc__ or ""
    assert "no-op" in reason and "append-only" in reason and "0003" in reason
    module.upgrade()
    assert len(executed) == 1
    assert executed[0].rstrip().endswith("ON CONFLICT (code) DO NOTHING")
    assert "DELETE" not in executed[0].upper()


def test_retention_schema_admits_the_refusing_default_and_full_mappings_only() -> None:
    """T-PLT-31 `platform.snapshot_retention_families` (04 rev 1.56; ci-stage returned item on main
    0cb36c14): the refusing default ``{}`` validates against its own schema — the catalogue
    invariant every storable default meets — a full mapping of the five families validates, and a
    partial mapping or an unknown key still refuses."""
    spec = PLATFORM_PARAMETERS["platform.snapshot_retention_families"]
    families = sorted(spec.value_schema["anyOf"][1]["properties"])
    assert families == [
        "contract_event",
        "file_object",
        "import_row",
        "manual_adjustment",
        "source_record",
    ]
    assert schema_errors(spec.value_schema, {}) == []
    assert schema_errors(spec.value_schema, spec.default_asc606) == []
    full = dict.fromkeys(families, "AUDIT_RETENTION_YEARS")
    assert schema_errors(spec.value_schema, full) == []
    assert schema_errors(spec.value_schema, {"file_object": "AUDIT_RETENTION_YEARS"}) != []
    assert schema_errors(spec.value_schema, {**full, "other": "FILE_RETENTION"}) != []
    assert schema_errors(spec.value_schema, {**full, "file_object": "FOREVER"}) != []


def test_snapshot_job_subject_type_is_a_t_plt_13_subject() -> None:
    """T-PLT-13 `ck_job__subject_type` admits a fixed list (revision 0012 ``SUBJECT_TYPES``); the
    TENANT_SNAPSHOT job's subject is the source ``tenant`` — ``tenant_snapshot`` is not a job
    subject type (the batch on main 0cb36c14 returned the 500 of POST /tenant/snapshots)."""
    module = _revision_module(REVISION.with_name("0012_numbering_and_jobs.py"))
    assert snapshots.JOB_SUBJECT_TYPE in module.SUBJECT_TYPES
    assert snapshots.OBJECT_TYPE not in module.SUBJECT_TYPES
