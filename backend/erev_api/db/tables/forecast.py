"""Forecast scenario, published input sets, runs and deal previews (T-FC-01 to T-FC-04)."""

from typing import Final

from sqlalchemy import CHAR, Column, Table, Text, Uuid, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from erev_api.db.tables import metadata
from erev_api.db.tables.platform import (
    _enum,
    _sc_c,
    _sc_c_sc_m,
    _sc_v,
    _timestamp,
    run_status_platform,
)
from erev_api.enums import ScenarioStatus

scenario_status: Final = _enum(ScenarioStatus, "scenario_status")
scenario: Final = Table(
    "scenario",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("name", Text(), nullable=False),
    Column("purpose", Text()),
    Column("scenario_tenant_id", Uuid(), nullable=False),
    Column("tenant_snapshot_id", Uuid(), nullable=False),
    _timestamp("base_known_at", nullable=False),
    Column("status", scenario_status, nullable=False, server_default=text("'ACTIVE'")),
    _timestamp("last_refreshed_at"),
    *_sc_c_sc_m(),
)
scenario_refresh: Final = Table(
    "scenario_refresh",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("scenario_id", Uuid(), nullable=False),
    Column("source_tenant_id", Uuid(), nullable=False),
    Column("source_input_set_id", Uuid(), nullable=False),
    Column("source_content_sha256", CHAR(64), nullable=False),
    Column("target_tenant_id", Uuid(), nullable=False),
    Column("tenant_snapshot_id", Uuid(), nullable=False),
    Column("job_id", Uuid(), nullable=False),
    Column("status", run_status_platform, nullable=False, server_default=text("'QUEUED'")),
    Column("target_input_set_id", Uuid()),
    Column("target_content_sha256", CHAR(64)),
    _timestamp("started_at"),
    _timestamp("finished_at"),
    Column("problem", JSONB(none_as_null=True)),
    *_sc_c_sc_m(),
)
forecast_event_set: Final = Table(
    "forecast_event_set",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("production_scenario_id", Uuid(), nullable=False),
    Column("import_upload_ids", ARRAY(Uuid()), nullable=False, server_default=text("'{}'")),
    Column("api_commands", JSONB(), nullable=False, server_default=text("'[]'::jsonb")),
    Column("input_sequence", JSONB(none_as_null=True), nullable=True),
    *_sc_c_sc_m(),
    *_sc_v(),
)
forecast_run: Final = Table(
    "forecast_run",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("forecast_event_set_id", Uuid(), nullable=False),
    Column("status", run_status_platform, nullable=False, server_default=text("'QUEUED'")),
    Column("parameters", JSONB(), nullable=False),
    Column("report_run_ids", ARRAY(Uuid()), nullable=False, server_default=text("'{}'")),
    Column("job_id", Uuid()),
    _timestamp("started_at"),
    _timestamp("finished_at"),
    Column("problem", JSONB(none_as_null=True)),
    *_sc_c_sc_m(),
)
deal_preview: Final = Table(
    "deal_preview",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("input", JSONB(), nullable=False),
    Column("input_sha256", CHAR(64), nullable=False),
    Column("result", JSONB(), nullable=False),
    Column("result_sha256", CHAR(64), nullable=False),
    Column("engine_release_id", Uuid(), nullable=False),
    Column("pinned_refs", JSONB(), nullable=False),
    Column("saved_contract_id", Uuid()),
    *_sc_c(),
)
