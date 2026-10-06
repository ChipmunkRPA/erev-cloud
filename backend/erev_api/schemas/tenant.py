"""API-R-04 Tenant schemas: the workspace row and its settings update (04 §15.3 API-R-04, T-PLT-01,
DB-05; SCREENS_B SF-23 data bindings; PRD ERR-26), and the tenant snapshot request and row
(T-PLT-34; BUILD_SPEC SNP-1 slice I-4)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from erev_api.enums import PrincipalKind, RunStatus, TenantKind, TenantStatus
from erev_api.schemas.common import ActorOut, JobOut
from erev_api.schemas.me import LOCALE_LENGTH
from erev_api.schemas.users import LABEL_LENGTH

SnapshotPurpose = Literal["SANDBOX_COPY", "STORED_BACKUP", "SANDBOX_SEED"]  # T-PLT-34 check


class TenantSandboxLoadOut(BaseModel):
    """API-S-Tenant ``sandbox_load`` (04 §16.14 rev 1.125; 05 SBX-04): what the sandbox's own
    ``tenant.snapshot_loaded`` event says about its load — the queryable home of
    ``blocked_periods`` and the seed snapshot a reset goes back to."""

    tenant_snapshot_id: uuid.UUID
    loaded_at: datetime
    derived_mismatches: int
    blocked_periods: list[uuid.UUID]
    load_report_file_id: uuid.UUID
    load_report_sha256: str


class TenantOut(BaseModel):
    """API-S-Tenant: the T-PLT-01 row without the HMAC key identifier (SPEC-Q-186), and for a
    sandbox loaded from a snapshot the facts of its load (rev 1.125)."""

    id: uuid.UUID
    code: str
    kind: TenantKind
    status: TenantStatus
    display_name: str
    reporting_currency: str
    source_tenant_id: uuid.UUID | None
    source_known_at: datetime | None
    is_demo: bool
    industry_cluster: str | None
    default_locale: str
    setup_completed_at: datetime | None
    ai_disabled_at: datetime | None
    ai_disabled_by: uuid.UUID | None
    ai_disabled_by_kind: PrincipalKind | None
    created_at: datetime
    created_by: uuid.UUID | None
    created_by_kind: PrincipalKind
    updated_at: datetime
    updated_by: uuid.UUID | None
    updated_by_kind: PrincipalKind
    row_version: int
    sandbox_load: TenantSandboxLoadOut | None = None


class TenantUpdateIn(BaseModel):
    """``PATCH /tenant``: any of ``display_name`` and ``default_locale``."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=LABEL_LENGTH)
    default_locale: str | None = Field(default=None, max_length=LOCALE_LENGTH)
    kind: str | None = Field(
        default=None,
        description="Never accepted: a workspace's type cannot change (409 tenant-kind-immutable).",
    )


class TenantSnapshotRequestIn(BaseModel):
    """``POST /tenant/snapshots`` (API-R-04; BUILD_SPEC SNP-1): the instant the copy is taken as of
    (with its UTC offset, API-C-07), the T-PLT-34 purpose and, for ``SANDBOX_COPY``, the sandbox
    name SNP-2 gives the tenant it creates."""

    model_config = ConfigDict(extra="forbid")

    known_at: AwareDatetime
    purpose: SnapshotPurpose
    name: str | None = Field(default=None, max_length=LABEL_LENGTH)


class TenantSnapshotOut(BaseModel):
    """The T-PLT-34 row; ``created_by`` is the API-S-Actor of who asked for the snapshot."""

    id: uuid.UUID
    known_at: datetime
    purpose: SnapshotPurpose
    status: RunStatus
    target_tenant_id: uuid.UUID | None
    manifest_file_id: uuid.UUID | None
    manifest_sha256: str | None
    row_counts: dict[str, int] | None
    job_id: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    created_by: ActorOut


class TenantSnapshotRequestedOut(JobOut):
    """The 202 body of ``POST /tenant/snapshots``: API-S-Job of the deferred ``TENANT_SNAPSHOT``
    job plus the id of the T-PLT-34 row it fills (also the ``X-Erev-Tenant-Snapshot-Id`` header)."""

    tenant_snapshot_id: uuid.UUID


class TenantSandboxRequestIn(BaseModel):
    """``POST /tenant/sandboxes`` (API-R-04 rev 1.67; BUILD_SPEC SNP-2): the stored ``SUCCEEDED``
    snapshot to restore and the name of the new sandbox (its code is derived; 04 T-PLT-34)."""

    tenant_snapshot_id: uuid.UUID
    name: str = Field(min_length=1, max_length=400)


class TenantSandboxRequestedOut(JobOut):
    """The 202 body of ``POST /tenant/sandboxes``: API-S-Job of the deferred load-only
    ``TENANT_SNAPSHOT`` job (``mode = "restore"``) plus the pre-allocated sandbox tenant id, also
    in the ``X-Erev-Sandbox-Tenant-Id`` header."""

    sandbox_tenant_id: uuid.UUID


ResetMode = Literal["SNAPSHOT", "EMPTY"]
RESET_REASON_LENGTH = range(10, 2001)  # SB-R-05 minimum; the comment length of BR-PLT-08


class TenantResetIn(BaseModel):
    """``POST /tenant/reset`` (API-R-04 rev 1.125; BUILD_SPEC SNP-3; 05 SBX-07): back to the
    sandbox's seed snapshot (the server resolves it; ``tenant_snapshot_id``, when sent, must name
    it) or to an empty workspace (``tenant_snapshot_id`` absent or null), with the reason of the
    high-risk confirmation."""

    model_config = ConfigDict(extra="forbid")

    mode: ResetMode
    tenant_snapshot_id: uuid.UUID | None = None
    reason: str = Field(max_length=RESET_REASON_LENGTH.stop - 1)


class TenantResetRequestedOut(JobOut):
    """The 202 body of ``POST /tenant/reset``: API-S-Job of the deferred ``SANDBOX_RESET`` job
    plus the pre-allocated successor sandbox, also in the ``X-Erev-Sandbox-Tenant-Id`` header."""

    sandbox_tenant_id: uuid.UUID
