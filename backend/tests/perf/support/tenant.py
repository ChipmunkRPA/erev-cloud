"""The perf tenant check (dev-guide DG-PERF-06; 05 PERF-11): ``perf-volume`` must exist with the
current manifest hash, month 23 locked and a succeeded stored snapshot — the ``STORED_BACKUP``
that ``erev perf seed --snapshot-only`` asks (DG-MK-perf-seed (5); a ``SANDBOX_SEED`` request
names a sandbox and loads it, 04 API-R-04) —; otherwise every perf test fails with one message."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from perf.support.rules import STALE_MESSAGE

TENANT_CODE: Final = "perf-volume"
SEED_PURPOSE: Final = "STORED_BACKUP"
SUCCEEDED: Final = "SUCCEEDED"


class PerfTenantStale(RuntimeError):
    """Raised with ``STALE_MESSAGE`` (the perf tests fail with it verbatim)."""


@dataclass(frozen=True, slots=True)
class SnapshotFacts:
    """The selected stored snapshot as the tenant read context returns it (T-PLT-34):
    its authoritative ``known_at`` and ``purpose`` travel into the restore (Codex 2316 R2 (b))."""

    snapshot_id: UUID
    status: str
    known_at: datetime
    purpose: str


@dataclass(frozen=True, slots=True)
class TenantFacts:
    """What the check reads about ``perf-volume``; ``None`` from the lookup means absent."""

    tenant_id: UUID
    industry_cluster: str | None
    month_23_locked: bool
    snapshot: SnapshotFacts | None


@dataclass(frozen=True, slots=True)
class PerfTenant:
    tenant_id: UUID
    industry_cluster: str
    snapshot: SnapshotFacts

    @property
    def seed_snapshot_id(self) -> UUID:
        return self.snapshot.snapshot_id


def compose_facts(
    directory: Callable[[], tuple[UUID, str | None] | None],
    snapshot_of: Callable[[UUID], SnapshotFacts | None],
) -> TenantFacts | None:
    """Two reads, two scopes (Codex 2316 R2 (a)): the tenant identity from the directory scope,
    then the snapshot in that tenant's authorised read context. The month-23 lock is evidenced by a
    succeeded stored snapshot, which ``erev perf seed`` asks only after the lock
    (DG-PERF-01)."""
    found = directory()
    if found is None:
        return None
    tenant_id, cluster = found
    snapshot = snapshot_of(tenant_id)
    return TenantFacts(
        tenant_id=tenant_id,
        industry_cluster=cluster,
        month_23_locked=snapshot is not None and snapshot.status == SUCCEEDED,
        snapshot=snapshot,
    )


def stale_reason(facts: TenantFacts | None, expected_cluster: str) -> str | None:
    """Why the tenant is missing or stale (for the record); None when it is current."""
    if facts is None:
        return "tenant perf-volume is absent"
    if facts.industry_cluster != expected_cluster:
        return (
            f"industry_cluster {facts.industry_cluster!r} is not the current manifest "
            f"{expected_cluster!r}"
        )
    if not facts.month_23_locked:
        return "month 23 is not locked for every entity and book"
    if facts.snapshot is None or facts.snapshot.status != SUCCEEDED:
        return f"no succeeded {SEED_PURPOSE} snapshot"
    if facts.snapshot.purpose != SEED_PURPOSE:
        return f"snapshot purpose {facts.snapshot.purpose!r} is not {SEED_PURPOSE}"
    return None


def check_perf_tenant(
    lookup: Callable[[], TenantFacts | None], *, expected_cluster: str
) -> PerfTenant:
    """``PerfTenant`` when current; ``PerfTenantStale(STALE_MESSAGE)`` otherwise (the reason is
    attached as a note for the log, never in the message the test asserts)."""
    facts = lookup()
    reason = stale_reason(facts, expected_cluster)
    if reason is not None or facts is None or facts.snapshot is None:
        error = PerfTenantStale(STALE_MESSAGE)
        error.add_note(reason or "unknown")
        raise error
    assert facts.industry_cluster is not None
    return PerfTenant(facts.tenant_id, facts.industry_cluster, facts.snapshot)
