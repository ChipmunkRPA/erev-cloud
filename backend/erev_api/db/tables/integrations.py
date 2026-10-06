"""Integration tables (04 §11)."""

from __future__ import annotations

from typing import Final

from sqlalchemy import Column, Integer, Table, Text, Uuid, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from erev_api.db.tables import metadata
from erev_api.db.tables.platform import _enum, _sc_c, _sc_c_sc_m, _timestamp
from erev_api.enums import OutboxStatus, OutboxTopic, SyncRunStatus

# Created by revision 0016 (PLF-14): E-70, E-71.
outbox_topic: Final = _enum(OutboxTopic, "outbox_topic")
outbox_status: Final = _enum(OutboxStatus, "outbox_status")

# T-INT-03: transactional outbox (IM-S, RLS-T); DB-03 trigger. Created in PLF (04 §18 rule 7(a)).
outbox_message: Final = Table(
    "outbox_message",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("topic", outbox_topic, nullable=False),
    Column("aggregate_type", Text(), nullable=False),
    Column("aggregate_id", Uuid(), nullable=False),
    Column("dedupe_key", Text(), nullable=False),
    Column("payload", JSONB(none_as_null=True), nullable=False),
    Column("status", outbox_status, nullable=False, server_default=text("'PENDING'")),
    Column("attempt_count", Integer(), nullable=False, server_default=text("0")),
    _timestamp("next_attempt_at", nullable=False, now_default=True),
    Column("last_error", Text(), nullable=True),
    _timestamp("dispatched_at"),
    *_sc_c_sc_m(),
)

# Created by revision 0072 (DIN-12): E-72.
sync_run_status: Final = _enum(SyncRunStatus, "sync_run_status")

# T-INT-01: a configured adapter instance (IM-M, DELETE forbidden; RLS-T; AUD-CMD, ``checkpoint``
# AUD-OPS). ``adapter``, ``direction``, ``status`` and ``last_test_result`` are text with CHECKs in
# the revision (04 §11); ``secret_ref`` names the secret and never holds it (REQ-INT-006). DB-15
# ``tg_integration_connection__sandbox``: in a sandbox tenant an outbound adapter other than CSV_GL
# cannot be ACTIVE. Created by revision 0072 (DIN-12).
integration_connection: Final = Table(
    "integration_connection",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("code", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("adapter", Text(), nullable=False),
    Column("direction", Text(), nullable=False),
    Column("entity_ids", ARRAY(Uuid()), nullable=False, server_default=text("'{}'::uuid[]")),
    Column("base_url", Text(), nullable=True),
    Column("config", JSONB(none_as_null=True), nullable=False, server_default=text("'{}'::jsonb")),
    Column("secret_ref", Text(), nullable=True),
    Column("status", Text(), nullable=False, server_default=text("'DISABLED'")),
    Column(
        "checkpoint", JSONB(none_as_null=True), nullable=False, server_default=text("'{}'::jsonb")
    ),
    _timestamp("last_test_at"),
    Column("last_test_result", Text(), nullable=True),
    Column("last_test_detail", Text(), nullable=True),
    *_sc_c_sc_m(),
)

# T-INT-02: the interface run ledger with control totals (IM-S: UPDATE of ``status``,
# ``checkpoint_after``, the totals, the counts, ``problem``, ``started_at``, ``finished_at``; RLS-T;
# DB-03 transition trigger). Created by revision 0072 (DIN-12).
sync_run: Final = Table(
    "sync_run",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("integration_connection_id", Uuid(), nullable=False),
    Column("kind", Text(), nullable=False),
    Column("status", sync_run_status, nullable=False, server_default=text("'QUEUED'")),
    Column("checkpoint_before", JSONB(none_as_null=True), nullable=True),
    Column("checkpoint_after", JSONB(none_as_null=True), nullable=True),
    Column("source_totals", JSONB(none_as_null=True), nullable=True),
    Column("loaded_totals", JSONB(none_as_null=True), nullable=True),
    Column("record_count", Integer(), nullable=False, server_default=text("0")),
    Column("exception_count", Integer(), nullable=False, server_default=text("0")),
    Column("problem", JSONB(none_as_null=True), nullable=True),
    Column("job_id", Uuid(), nullable=True),
    _timestamp("started_at"),
    _timestamp("finished_at"),
    *_sc_c_sc_m(),
)

# T-INT-04: internal ↔ external ids per connection (IM-S: UPDATE ``valid_to`` only — a re-link
# inserts a new row; RLS-T; AUD-FACT; SC-C only). Created by revision 0072 (DIN-12).
external_id_map: Final = Table(
    "external_id_map",
    metadata,
    Column("tenant_id", Uuid(), primary_key=True),
    Column("id", Uuid(), primary_key=True),
    Column("integration_connection_id", Uuid(), nullable=False),
    Column("object_type", Text(), nullable=False),
    Column("internal_id", Uuid(), nullable=False),
    Column("external_id", Text(), nullable=False),
    Column("external_version", Text(), nullable=True),
    _timestamp("valid_from", nullable=False, now_default=True),
    _timestamp("valid_to"),
    Column("sync_run_id", Uuid(), nullable=True),
    *_sc_c(),
)
