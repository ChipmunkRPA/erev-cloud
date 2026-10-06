"""Slice I-4 (lane record §13.2.10): the pure parts of the snapshot routes — the request checks
(API-R-04 ``POST /tenant/snapshots``; 05 SBX-02; PRD ACT-50), the list spec of
``GET /tenant/snapshots`` and the schemas. The route module stays clear of the handler module
(DG-ARC-08): collecting a route registers no job kind."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from erev_api.domain.platform import snapshots
from erev_api.enums import RunStatus, TenantKind
from erev_api.problems import Problem
from erev_api.schemas.users import LABEL_LENGTH

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
ROUTE = Path(__file__).resolve().parents[2] / "erev_api/api/v1/tenant.py"


def test_check_request_refuses_by_name() -> None:
    accepted = snapshots.check_request(
        kind=TenantKind.PRODUCTION,
        known_at=NOW - timedelta(hours=1),
        purpose="STORED_BACKUP",
        now=NOW,
    )
    assert accepted.known_at == NOW - timedelta(hours=1)
    assert accepted.purpose == "STORED_BACKUP" and accepted.sandbox_name is None
    with pytest.raises(Problem) as future:
        snapshots.check_request(
            kind=TenantKind.PRODUCTION,
            known_at=NOW + timedelta(seconds=1),
            purpose="STORED_BACKUP",
            now=NOW,
        )
    assert future.value.slug == "validation-failed" and future.value.errors[0].field == "known_at"
    with pytest.raises(Problem) as sandbox:
        snapshots.check_request(
            kind=TenantKind.SANDBOX, known_at=NOW, purpose="STORED_BACKUP", now=NOW
        )
    assert sandbox.value.slug == "sandbox-restricted"  # 05 SBX-02: a production source only
    with pytest.raises(Problem) as purpose:
        snapshots.check_request(
            kind=TenantKind.PRODUCTION, known_at=NOW, purpose="ARCHIVE", now=NOW
        )
    assert purpose.value.slug == "validation-failed" and purpose.value.errors[0].field == "purpose"
    with pytest.raises(Problem) as naive:
        snapshots.check_request(
            kind=TenantKind.PRODUCTION,
            known_at=NOW.replace(tzinfo=None),
            purpose="STORED_BACKUP",
            now=NOW,
        )
    assert naive.value.slug == "validation-failed"
    with pytest.raises(Problem) as long_name:
        snapshots.check_request(
            kind=TenantKind.PRODUCTION,
            known_at=NOW,
            purpose="SANDBOX_COPY",
            now=NOW,
            sandbox_name="x" * (LABEL_LENGTH + 1),
        )
    assert long_name.value.slug == "validation-failed" and long_name.value.errors[0].field == "name"


def test_step_up_is_required_within_the_window() -> None:
    snapshots.require_fresh_step_up(NOW - timedelta(minutes=4), NOW)  # BR-PLT-06: fresh enough
    with pytest.raises(Problem) as stale:
        snapshots.require_fresh_step_up(NOW - timedelta(minutes=6), NOW)
    assert stale.value.slug == "mfa-step-up-required"
    with pytest.raises(Problem) as never:
        snapshots.require_fresh_step_up(None, NOW)
    assert never.value.slug == "mfa-step-up-required"


def test_job_params_are_the_handler_params() -> None:
    params = snapshots.job_params(UUID(int=1), NOW, "STORED_BACKUP", None)
    assert params == {
        "tenant_snapshot_id": str(UUID(int=1)),
        "known_at": "2026-09-20T12:00:00+00:00",
        "purpose": "STORED_BACKUP",
    }
    with_name = snapshots.job_params(UUID(int=1), NOW, "SANDBOX_COPY", "Scenario A")
    assert with_name["sandbox_name"] == "Scenario A"  # SNP-2 reads it; T-PLT-34 has no name


def test_list_spec_sorts_and_filters() -> None:
    from erev_api.api.v1 import tenant as tenant_routes

    spec = tenant_routes.SNAPSHOT_LIST
    assert spec.resource == "tenant-snapshots" and spec.default_sort == "-created_at"
    assert set(spec.sort_keys) == {"id", "created_at", "known_at"}
    assert spec.filters["status"].choices == frozenset(status.value for status in RunStatus)
    assert spec.filters["purpose"].choices == frozenset(
        {"SANDBOX_COPY", "STORED_BACKUP", "SANDBOX_SEED"}
    )


def test_schemas_pin_the_literals() -> None:
    from erev_api.schemas.tenant import (
        TenantSnapshotOut,
        TenantSnapshotRequestedOut,
        TenantSnapshotRequestIn,
    )

    body = TenantSnapshotRequestIn.model_validate(
        {"known_at": "2026-09-20T11:00:00Z", "purpose": "STORED_BACKUP"}
    )
    assert body.name is None and body.known_at.tzinfo is not None
    with pytest.raises(ValueError):  # a naive instant is refused (API-C-07)
        TenantSnapshotRequestIn.model_validate(
            {"known_at": "2026-09-20T11:00:00", "purpose": "STORED_BACKUP"}
        )
    with pytest.raises(ValueError):
        TenantSnapshotRequestIn.model_validate(
            {"known_at": "2026-09-20T11:00:00Z", "purpose": "ARCHIVE"}
        )
    with pytest.raises(ValueError):
        TenantSnapshotRequestIn.model_validate(
            {"known_at": "2026-09-20T11:00:00Z", "purpose": "STORED_BACKUP", "extra": 1}
        )
    fields = TenantSnapshotRequestedOut.model_fields
    assert "tenant_snapshot_id" in fields and "id" in fields and "state" in fields
    assert set(TenantSnapshotOut.model_fields) >= {
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
    }


def test_route_module_declares_the_snapshot_routes_without_the_handler() -> None:
    text = ROUTE.read_text(encoding="utf-8")
    for operation in (
        "tenant_snapshots_request",
        "tenant_snapshots_list",
        "tenant_snapshots_get",
        "tenant_snapshots_manifest",
    ):
        assert f'operation_id="{operation}"' in text, operation
    assert "snapshot_job" not in text  # DG-ARC-08: the route never imports the handler
