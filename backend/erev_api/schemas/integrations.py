"""API-R-45 integrations: connections, sync runs and external ids (04 §15.3 API-R-45; T-INT-01,
T-INT-02, T-INT-04; E-72; §16.14 — "Integration connections add ``last_sync_run`` … sync runs add
``duration_seconds``"; SCREENS §14.3 bindings; PRD BR-INT-01; BUILD_SPEC DIN-12).

The shapes restate the 04 table columns: ``secret_ref`` is the reference of the secret in the key
provider's secret store, inside the workspace's own namespace (04 T-INT-01 rev 1.108), and never
its value (REQ-INT-006); the text columns carry the 04 CHECK lists as literals here, not as
E-numbers (``enums.py`` mirrors 04 §3 only).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from erev_api.enums import SyncRunStatus

Adapter = Literal["SALESFORCE", "STRIPE", "NETSUITE", "QUICKBOOKS_ONLINE", "CSV_GL"]
Direction = Literal["INBOUND", "OUTBOUND", "BOTH"]
ConnectionStatus = Literal["ACTIVE", "DISABLED"]
TestResult = Literal["SUCCESS", "FAILURE"]
SyncRunKind = Literal[
    "INBOUND_POLL",
    "WEBHOOK_BATCH",
    "RECONCILIATION_SWEEP",
    "COA_SYNC",
    "TRIAL_BALANCE_PULL",
    "JOURNAL_EXPORT",
    "TEST_CONNECTION",
]
ExternalObjectType = Literal[
    "legal_entity",
    "gl_account",
    "dimension_value",
    "customer",
    "product",
    "contract",
    "obligation",
    "journal_batch",
]

SECRET_REF_DESCRIPTION = (
    "Reference of the adapter secret in the key provider's secret store: `<secret name>@<version>`"
    " under the hosted provider. The secret's name begins with `tenant-<tenant id>-`, the"
    " workspace's own namespace; any other reference is refused with 422. The value is never"
    " stored or returned (REQ-INT-006)"
)


class IntegrationConnectionIn(BaseModel):
    """``POST /integrations``: a T-INT-01 connection; it starts DISABLED."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    adapter: Adapter
    direction: Direction
    owner_membership_id: uuid.UUID | None = Field(
        default=None, description="Member responsible for integration exceptions"
    )
    entity_ids: list[uuid.UUID] = Field(default_factory=list, description="Empty = all entities")
    base_url: str | None = Field(default=None, description="Mock server URL in tests and demos")
    config: dict[str, Any] = Field(default_factory=dict, description="Non-secret settings")
    secret_ref: str | None = Field(default=None, description=SECRET_REF_DESCRIPTION)


class IntegrationConnectionUpdateIn(BaseModel):
    """``PATCH /integrations/{id}`` (If-Match): the mutable T-INT-01 members; an omitted member
    keeps its value."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    entity_ids: list[uuid.UUID] | None = None
    base_url: str | None = None
    config: dict[str, Any] | None = None
    secret_ref: str | None = Field(default=None, description=SECRET_REF_DESCRIPTION)
    status: ConnectionStatus | None = None
    owner_membership_id: uuid.UUID | None = None


class SyncRunResultOut(BaseModel):
    """The counts of a finished run (04 §16.14 ``last_sync_run.result``)."""

    record_count: int
    exception_count: int


class LastSyncRunOut(BaseModel):
    """04 §16.14: ``last_sync_run`` of a connection — the newest run by ``created_at``."""

    id: uuid.UUID
    status: SyncRunStatus
    finished_at: datetime | None
    result: SyncRunResultOut


class IntegrationConnectionOut(BaseModel):
    """API-S-IntegrationConnection: the T-INT-01 row (``secret_ref`` as the reference name) plus
    ``last_sync_run`` (04 §16.14)."""

    id: uuid.UUID
    code: str
    name: str
    adapter: Adapter
    direction: Direction
    entity_ids: list[uuid.UUID]
    owner_membership_id: uuid.UUID | None
    base_url: str | None
    config: dict[str, Any]
    secret_ref: str | None
    status: ConnectionStatus
    checkpoint: dict[str, Any]
    last_test_at: datetime | None
    last_test_result: TestResult | None
    last_test_detail: str | None
    last_sync_run: LastSyncRunOut | None
    created_at: datetime
    updated_at: datetime
    row_version: int


class SyncRequestIn(BaseModel):
    """``POST /integrations/{id}/sync``: the kind of run to queue (SCREENS §14.3 "Run sync")."""

    model_config = ConfigDict(extra="forbid")

    kind: SyncRunKind = "INBOUND_POLL"


class SyncRunOut(BaseModel):
    """API-S-SyncRun: the T-INT-02 row plus ``duration_seconds`` (04 §16.14: ``finished_at`` −
    ``started_at`` in whole seconds, null while running)."""

    id: uuid.UUID
    integration_connection_id: uuid.UUID
    kind: SyncRunKind
    status: SyncRunStatus
    checkpoint_before: dict[str, Any] | None
    checkpoint_after: dict[str, Any] | None
    source_totals: dict[str, Any] | None
    loaded_totals: dict[str, Any] | None
    record_count: int
    exception_count: int
    problem: dict[str, Any] | None
    job_id: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    duration_seconds: int | None
    created_at: datetime
    updated_at: datetime
    row_version: int


class ExternalIdMapIn(BaseModel):
    """``POST /external-ids`` (04 §16.14 rev 1.81; `masterdata.maintain`): a live T-INT-04 link —
    the alias J-23.5 adds; a superseded live link of the same external or internal id is closed."""

    model_config = ConfigDict(extra="forbid")

    integration_connection_id: uuid.UUID
    object_type: ExternalObjectType
    internal_id: uuid.UUID
    external_id: str = Field(min_length=1, max_length=200)
    external_version: str | None = Field(default=None, max_length=200)


class ExternalIdMapOut(BaseModel):
    """API-S-ExternalIdMap: the T-INT-04 row."""

    id: uuid.UUID
    integration_connection_id: uuid.UUID
    object_type: ExternalObjectType
    internal_id: uuid.UUID
    external_id: str
    external_version: str | None
    valid_from: datetime
    valid_to: datetime | None
    sync_run_id: uuid.UUID | None
    created_at: datetime


class WebhookAcceptedOut(BaseModel):
    """``POST /webhooks/{adapter}/{connection_id}`` 202 (05 ADP-01): the ``WEBHOOK_BATCH`` sync run
    that recorded the notification ids and the ``SYNC_RUN`` job deferred to fetch each object."""

    sync_run_id: uuid.UUID
    job_id: uuid.UUID
    notifications: int
    received_at: AwareDatetime
