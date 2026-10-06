"""T-MIG-01 to T-MIG-03 on the lane branch (BUILD_SPEC LMG-1; 04 §17 rev 1.35; §14.1 DB-01, DB-03;
PRD SM-12; lane record docs/reviews/loop/prod/F-LMG.md §16). CPU-only: the provisional revision
module is imported as a file and its constants compared with the registry rendering, the E-75 /
E-76 enums and the pure measure list; the row builders cover every NOT NULL column.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import get_args
from uuid import UUID

from erev_api.db.tables import (
    metadata,
    migrated_legacy_row,
    migration_batch,
    migration_population_obligation,
    migration_population_version,
    migration_reconciliation_line,
)
from erev_api.db.tables import migration as tables_migration
from erev_api.db.transitions import TRANSITIONS, transition_trigger_sql
from erev_api.domain.migration import reconciliation
from erev_api.domain.reports.builders import migration_reconciliation as report
from erev_api.enums import MigrationMode, MigrationStatus
from erev_api.schemas import migrations as schemas
from support.rows import (
    ROW_BUILDERS,
    migrated_legacy_row_values,
    migration_batch_values,
    migration_population_obligation_values,
    migration_population_version_values,
    migration_reconciliation_line_values,
)

REVISION = (
    Path(__file__).resolve().parents[2] / "erev_api/db/migrations/versions/0056_lmg_t_mig_01_03.py"
)
CHAIN = (
    "UPLOADED",
    "PROFILING",
    "PROFILED",
    "IMPORTING",
    "IMPORTED",
    "RECONCILED",
    "SUBMITTED",
    "PROMOTED",
)


def _load_revision(name: str) -> object:
    path = REVISION.parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"lmg_revision_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _revision_module() -> object:
    spec = importlib.util.spec_from_file_location("lmg_t_mig_revision", REVISION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_revision_is_provisional_and_matches_the_registries() -> None:
    module: object = _revision_module()
    # assigned id and parent (merge prep 2026-09-20; drafted as provisional 0098 on 0054)
    assert (module.revision, module.down_revision) == ("0056", "0055")  # type: ignore[attr-defined]
    assert "0098 on 0054" in (module.__doc__ or "")  # the drafting history stays named
    # 0067 (04 rev 1.60) REPLACES the DB-03 body with ``capture_operation_id`` among the updatable
    # columns; 0056's literal is the historical body 0067's downgrade restores.
    replacement = _load_revision("0067_lmg_t_mig_04_05")
    assert replacement.TRANSITION_BODY == transition_trigger_sql("migration_batch")  # type: ignore[attr-defined]
    assert replacement.TRANSITION_BODY_0056 == module.TRANSITION_BODY  # type: ignore[attr-defined]
    assert "capture_operation_id" in replacement.TRANSITION_BODY  # type: ignore[attr-defined]
    # D-98 candidate 128: the cutover is updatable and set once (the 0056 body froze it)
    assert "cutover_date of %I.%I is already set" in replacement.TRANSITION_BODY  # type: ignore[attr-defined]
    assert "cutover_date" not in module.TRANSITION_BODY  # type: ignore[attr-defined]
    assert (
        replacement.CUTOVER_CHECK_SQL_0056
        == dict(module.BATCH_CHECKS)["ck_migration_batch__cutover"]
    )  # type: ignore[attr-defined]
    assert replacement.CUTOVER_CHECK_SQL == (  # type: ignore[attr-defined]
        "(mode = 'REPLAY' AND cutover_date IS NULL) OR mode = 'OPENING_BALANCES'"
    )
    assert "capture_operation_id" not in module.TRANSITION_BODY  # type: ignore[attr-defined]
    assert set(module.BATCH_UPDATE_COLUMNS) | {"capture_operation_id", "cutover_date"} == {  # type: ignore[attr-defined]
        "status",
        *TRANSITIONS["migration_batch"].updatable_columns,
    }
    assert module.MIGRATION_MODE == tuple(m.value for m in MigrationMode)  # type: ignore[attr-defined]
    assert module.MIGRATION_STATUS == tuple(s.value for s in MigrationStatus)  # type: ignore[attr-defined]
    assert module.MEASURES == reconciliation.MEASURES == tables_migration.MEASURES  # type: ignore[attr-defined]
    assert module.LEGACY_ROW_LABEL == tables_migration.LEGACY_ROW_LABEL  # type: ignore[attr-defined]
    assert tables_migration.LEGACY_ROW_LABEL == "migrated, unattributed"
    assert "'ORIGINAL_ALLOCATION'" in module.LINE_CHECKS[0][1]  # type: ignore[attr-defined]
    checks = dict(module.LINE_CHECKS)  # type: ignore[attr-defined]
    assert checks["ck_migration_reconciliation_line__exception"] == (
        "is_within_tolerance OR deviation_ref IS NOT NULL OR exception_item_id IS NOT NULL"
    )
    assert module.TABLES == (  # type: ignore[attr-defined]
        "migration_batch",
        "migrated_legacy_row",
        "migration_reconciliation_line",
    )


def test_tables_follow_04_rev_1_35() -> None:
    assert [c.name for c in migration_batch.columns] == [
        "tenant_id",
        "id",
        "migration_no",
        "mode",
        "status",
        "source_file_id",
        "source_sha256",
        "cutover_date",
        "sandbox_tenant_id",
        "profile",
        "import_upload_ids",
        "registry_version_id",
        "reconciliation_id",
        "reconciliation_report_run_id",
        "approval_request_id",
        "job_id",
        "started_at",
        "finished_at",
        "problem",
        "capture_operation_id",
        "created_at",
        "created_by",
        "created_by_kind",
        "updated_at",
        "updated_by",
        "updated_by_kind",
        "row_version",
    ]
    assert [c.name for c in migrated_legacy_row.columns] == [
        "tenant_id",
        "id",
        "migration_batch_id",
        "source_rowid",
        "contract_external_id",
        "obligation_key",
        "product_code",
        "current_period",
        "processing_time_log",
        "record_unique_id",
        "legacy_row",
        "legacy_row_sha256",
        "contract_id",
        "obligation_id",
        "label",
        "created_at",
        "created_by",
        "created_by_kind",
    ]
    assert [c.name for c in migration_reconciliation_line.columns] == [
        "tenant_id",
        "id",
        "migration_batch_id",
        "contract_external_id",
        "obligation_key",
        "measure",
        "source_value",
        "erev_value",
        "difference",
        "tolerance",
        "is_within_tolerance",
        "deviation_ref",
        "exception_item_id",
        "created_at",
        "created_by",
        "created_by_kind",
    ]
    assert {
        "erev.migration_batch",
        "erev.migrated_legacy_row",
        "erev.migration_reconciliation_line",
    } <= set(metadata.tables)
    assert str(migration_reconciliation_line.c.tolerance.server_default.arg) == "0.0001"  # type: ignore[union-attr]
    assert str(migrated_legacy_row.c.label.server_default.arg) == "'migrated, unattributed'"  # type: ignore[union-attr]
    assert str(migration_batch.c.status.server_default.arg) == "'UPLOADED'"  # type: ignore[union-attr]


def test_capture_tables_follow_04_rev_1_60() -> None:
    # T-MIG-04 / T-MIG-05 (revision 0067): column order as 04 lists it (DG-ARC-09 compares too);
    # the token columns carry no foreign key (they name rolled-back rows); the book is ASC606.
    assert [c.name for c in migration_population_version.columns] == [
        "tenant_id",
        "id",
        "migration_batch_id",
        "contract_version_id",
        "version_no",
        "book_code",
        "combination_group_id",
        "status_in_book",
        "contract_computation_id",
        "input_sha256",
        "output_sha256",
        "engine_version",
        "engine_release_id",
        "known_at",
        "bundle_known_at",
        "cutover_date",
        "payload_migration_batch_id",
        "opening_event_id",
        "opening_event_key",
        "opening_event_binding_sha256",
        "members",
        "expected_output_captured",
        "obligation_version_ids",
        "capture_operation_id",
        "calc_trace_id",
        "format_version",
        "node_count",
        "root_measures",
        "trace_sha256",
        "trace",
        "input_evidence",
        "input_evidence_sha256",
        "created_at",
        "created_by",
        "created_by_kind",
    ]
    assert [c.name for c in migration_population_obligation.columns] == [
        "tenant_id",
        "id",
        "migration_batch_id",
        "population_version_id",
        "capture_operation_id",
        "contract_version_id",
        "obligation_version_id",
        "contract_id",
        "contract_external_id",
        "obligation_key",
        "obligation_kind",
        "original_allocated_exact",
        "remaining_quantity",
        "billed_cum",
        "revenue_cum",
        "remaining_allocation",
        "position_obligation",
        "netting_reclass_amount",
        "trace_nodes",
        "row",
        "row_sha256",
        "created_at",
        "created_by",
        "created_by_kind",
    ]
    assert tables_migration.POPULATION_BOOK == "ASC606"
    assert str(migration_population_version.c.obligation_version_ids.server_default.arg) == (  # type: ignore[union-attr]
        "'{}'::uuid[]"
    )
    version_module = _load_revision("0067_lmg_t_mig_04_05")
    # re-pointed onto F-SNP's 0066 (T-PLT-47) at the single main merge after F-SNP landed (main
    # fe8e85df, 2026-09-21; the ENG-C6 0064 precedent)
    assert version_module.down_revision == "0066"  # type: ignore[attr-defined]
    assert "never two heads on main" in (version_module.__doc__ or "")
    assert version_module.TABLES == (  # type: ignore[attr-defined]
        "migration_population_version",
        "migration_population_obligation",
    )
    checks = dict(version_module.VERSION_CHECKS)  # type: ignore[attr-defined]
    assert checks["ck_migration_population_version__book"] == "book_code = 'ASC606'"
    assert checks["ck_migration_population_version__payload_batch"] == (
        "payload_migration_batch_id = migration_batch_id"
    )
    assert "jsonb_array_length(members) >= 1" in checks["ck_migration_population_version__members"]
    # the migration's column list equals the metadata's (own columns, SC-C excluded)
    source = Path(version_module.__file__ or "").read_text(encoding="utf-8")  # type: ignore[arg-type]
    for table in (migration_population_version, migration_population_obligation):
        for column in table.columns:
            if column.name not in {
                "tenant_id",
                "id",
                "created_at",
                "created_by",
                "created_by_kind",
            }:
                assert f'"{column.name}"' in source, (table.name, column.name)


def test_e76_transitions_follow_sm_12() -> None:
    spec = TRANSITIONS["migration_batch"]
    assert spec.status_column == "status"
    expected = {*zip(CHAIN, CHAIN[1:], strict=False)}
    expected |= {(status, "FAILED") for status in CHAIN[:-1]}
    expected |= {(status, "CANCELLED") for status in CHAIN[:-1]}
    assert spec.pairs == frozenset(expected)
    terminal = {"PROMOTED", "FAILED", "CANCELLED"}
    assert not {pair for pair in spec.pairs if pair[0] in terminal}
    frozen = {"migration_no", "mode", "source_file_id", "source_sha256"}
    assert frozen.isdisjoint(spec.updatable_columns)
    assert {
        "profile",
        "import_upload_ids",
        "job_id",
        "problem",
        "row_version",
        "capture_operation_id",  # rev 1.60: the import's durable operation identity
        "cutover_date",  # rev 1.60 in place (D-98 cand. 128): set once at /import
    } <= spec.updatable_columns
    assert spec.set_once == frozenset({"cutover_date"})


def test_row_builders_cover_every_not_null_column() -> None:
    batch = migration_batch_values(UUID(int=1), source_file_id=UUID(int=2))
    legacy = migrated_legacy_row_values(UUID(int=1), migration_batch_id=UUID(int=3))
    line = migration_reconciliation_line_values(UUID(int=1), migration_batch_id=UUID(int=3))
    version = migration_population_version_values(UUID(int=1), migration_batch_id=UUID(int=3))
    captured = migration_population_obligation_values(
        UUID(int=1), migration_batch_id=UUID(int=3), population_version_id=version["id"]
    )
    for table, values in (
        (migration_batch, batch),
        (migrated_legacy_row, legacy),
        (migration_reconciliation_line, line),
        (migration_population_version, version),
        (migration_population_obligation, captured),
    ):
        required = {c.name for c in table.columns if not c.nullable and c.server_default is None}
        assert required <= set(values), (table.name, required - set(values))
    assert batch["status"] == "UPLOADED" and batch["mode"] == "OPENING_BALANCES"
    assert legacy["label"] == "migrated, unattributed" and len(legacy["legacy_row"]) == 71
    assert line["measure"] == "TRANSACTION_PRICE" and line["is_within_tolerance"] is True
    assert {
        "migration_batch",
        "migrated_legacy_row",
        "migration_reconciliation_line",
        "migration_population_version",
        "migration_population_obligation",
    } <= set(ROW_BUILDERS)
    assert version["payload_migration_batch_id"] == version["migration_batch_id"]
    assert captured["obligation_version_id"] == UUID(captured["row"]["id"])


def test_measure_mirror_of_04_rev_1_35() -> None:
    # the CHECK literal list, the pure module, the API literal and the RPT-41 labels agree
    assert get_args(schemas.Measure) == reconciliation.MEASURES
    assert tuple(report.MEASURE_LABELS) == reconciliation.MEASURES
    assert report.MEASURE_LABELS["ORIGINAL_ALLOCATION"] == "Original allocation"
    assert reconciliation.OBLIGATION_MEASURES[:2] == ("ORIGINAL_ALLOCATION", "ALLOCATION")
    assert "ORIGINAL_ALLOCATION" not in reconciliation.CONTRACT_MEASURES
