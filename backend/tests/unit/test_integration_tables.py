"""DIN-12 schema (04 T-INT-01, T-INT-02, T-INT-04; E-72; DB-15; revision 0072): the table
objects, the migration's CHECK lists and trigger bodies, and the E-72 type agree with 04 and with
the registries the guards read (DG-MIG-12 literal labels; DB-03 bodies rendered from
``erev_api.db.transitions``, compared by DG-ARC-07). CPU only — no database.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, Final, get_args

from erev_api.db.tables import external_id_map, integration_connection, sync_run
from erev_api.db.transitions import TRANSITIONS, transition_trigger_sql
from erev_api.enums import SyncRunStatus
from erev_api.schemas import integrations as schemas

VERSIONS: Final = (
    Path(__file__).resolve().parents[2] / "erev_api" / "db" / "migrations" / "versions"
)


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _revision() -> Any:
    return _load("0072_din_12_integrations")


def test_e_72_type_is_created_with_the_mirror_labels_in_04_order() -> None:
    module = _revision()
    assert module.revision == "0072"
    assert module.SYNC_RUN_STATUS == tuple(status.value for status in SyncRunStatus)
    assert module.SYNC_RUN_STATUS == (
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "CONTROL_TOTAL_MISMATCH",
        "FAILED",
    )


def test_check_lists_equal_the_api_literals() -> None:
    module = _revision()
    assert module.ADAPTERS == get_args(schemas.Adapter)
    assert module.DIRECTIONS == get_args(schemas.Direction)
    assert module.CONNECTION_STATUSES == get_args(schemas.ConnectionStatus)
    assert module.TEST_RESULTS == get_args(schemas.TestResult)
    assert module.SYNC_RUN_KINDS == get_args(schemas.SyncRunKind)
    assert module.OBJECT_TYPES == get_args(schemas.ExternalObjectType)


def test_transition_bodies_are_rendered_from_the_registry() -> None:
    module = _revision()
    assert module.SYNC_RUN_TRANSITION_BODY == transition_trigger_sql("sync_run")
    assert module.EXTERNAL_ID_MAP_TRANSITION_BODY == transition_trigger_sql("external_id_map")
    spec = TRANSITIONS["sync_run"]
    assert spec.status_column == "status"
    # The GRANT list carries ``status`` (erev_app updates it); the registry lists it as the status
    # column, never among the updatable columns (DB-03). SC-M is part of BOTH (04 T-INT-02 class
    # header): every move of a run stamps it, and a column missing from the grant is 42501 for the
    # whole UPDATE — the SYNC_RUN job then fails ``forbidden`` before it starts.
    assert set(module.SYNC_RUN_UPDATE_COLUMNS) - {"status"} == spec.updatable_columns
    assert {"row_version", "updated_at", "updated_by", "updated_by_kind"} <= set(
        module.SYNC_RUN_UPDATE_COLUMNS
    )
    assert "status" in module.SYNC_RUN_UPDATE_COLUMNS
    assert len(module.SYNC_RUN_UPDATE_COLUMNS) == len(set(module.SYNC_RUN_UPDATE_COLUMNS))
    assert spec.pairs == {
        ("QUEUED", "RUNNING"),
        ("RUNNING", "SUCCEEDED"),
        ("RUNNING", "CONTROL_TOTAL_MISMATCH"),
        ("RUNNING", "FAILED"),
        ("QUEUED", "FAILED"),
    }
    link = TRANSITIONS["external_id_map"]
    assert link.status_column is None
    assert link.updatable_columns == {"valid_to"} and link.set_once == {"valid_to"}


def test_tables_follow_04_t_int_01_02_04() -> None:
    connection = {c.name for c in integration_connection.columns}
    assert connection >= {
        "tenant_id",
        "id",
        "code",
        "name",
        "adapter",
        "direction",
        "entity_ids",
        "base_url",
        "config",
        "secret_ref",
        "status",
        "checkpoint",
        "last_test_at",
        "last_test_result",
        "last_test_detail",
        "created_at",
        "updated_at",
        "row_version",
    }
    # REQ-INT-006: the reference name only — there is no secret column to hold a value.
    assert not {name for name in connection if "secret" in name} - {"secret_ref"}
    run = {c.name for c in sync_run.columns}
    assert run >= {
        "integration_connection_id",
        "kind",
        "status",
        "checkpoint_before",
        "checkpoint_after",
        "source_totals",
        "loaded_totals",
        "record_count",
        "exception_count",
        "problem",
        "job_id",
        "started_at",
        "finished_at",
        "row_version",
    }
    assert str(sync_run.c.status.type.name) == "sync_run_status"
    link = {c.name for c in external_id_map.columns}
    assert link == {
        "tenant_id",
        "id",
        "integration_connection_id",
        "object_type",
        "internal_id",
        "external_id",
        "external_version",
        "valid_from",
        "valid_to",
        "sync_run_id",
        "created_at",
        "created_by",
        "created_by_kind",
    }


def test_db_15_sandbox_trigger_guards_outbound_activation_only() -> None:
    body = _revision().CONNECTION_SANDBOX_BODY
    assert "EREV-SBX-001" in body
    # INBOUND connections and CSV_GL never trip it; only ACTIVE outbound adapters in a sandbox do.
    assert "NEW.direction = 'INBOUND'" in body and "NEW.adapter = 'CSV_GL'" in body
    assert "tenant_kind = 'sandbox'" in body


def test_waiting_foreign_keys_target_sync_run() -> None:
    module = _revision()
    assert module.WAITING_KEYS == (
        ("source_record", "sync_run_id"),
        ("exception_item", "sync_run_id"),
    )
