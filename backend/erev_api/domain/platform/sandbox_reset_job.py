"""``SANDBOX_RESET`` job handler (BUILD_SPEC SNP-3; 05 §10 SBX-07 rev 1.64; 05 §5.6 execution
profile row — queue ``maintenance``, no retry, lock ``tenant-copy:<source tenant>``, 1,800 s).

The handler parses the params the request wrote and runs ``sandbox_reset.reset_sandbox`` in the
sandbox the reset supersedes; its failure hook archives a successor whose load failed. The job
row stays in the superseded sandbox: once the requester's session has moved, the outcome is read
as ``GET /tenant`` of the successor (04 API-R-04 rev 1.125).

Registration: ``jobs.registry.task`` on import; the worker's ``HANDLER_MODULES`` names this module,
so ``SANDBOX_RESET`` left ``PENDING_JOB_HANDLERS``. No route imports this module (DG-ARC-08).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final
from uuid import UUID

from erev_api.domain.platform import sandbox_reset
from erev_api.enums import JobKind
from erev_api.jobs.context import JobContext
from erev_api.jobs.registry import JobOutcome, RetryPolicy, task

__all__ = ["RESET_RETRY", "TENANT_HREF", "sandbox_reset_job"]

RESET_RETRY: Final = RetryPolicy(max_attempts=1)  # 05 §5.6: SANDBOX_RESET retries none
TENANT_HREF: Final = "/api/v1/tenant"


@task(JobKind.SANDBOX_RESET, retry=RESET_RETRY, on_failure=sandbox_reset.reset_failed)
def sandbox_reset_job(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``SANDBOX_RESET``: supersede the job's sandbox by a successor loaded from its seed snapshot
    or created empty, archive it and move the requester's sessions (05 SBX-07)."""
    parsed = sandbox_reset.parse_reset(params)
    outcome = sandbox_reset.reset_sandbox(
        jc, parsed, heartbeat=jc.heartbeat, refresh_snapshot=_export_latest
    )
    counts: dict[str, Any] = {"sessions_moved": outcome.sessions_moved}
    if outcome.loaded is not None:
        counts.update(
            {
                "loaded_rows": outcome.loaded.rows,
                "groups_recomputed": outcome.loaded.groups_recomputed,
                "groups_not_recomputed": outcome.loaded.groups_not_recomputed,
                "derived_mismatches": outcome.loaded.derived_mismatches,
                "blocked_periods": outcome.loaded.blocked_periods,
            }
        )
    return JobOutcome(
        state="SUCCEEDED",
        result={
            "href": TENANT_HREF,
            "counts": counts,
            "sandbox_tenant_id": str(outcome.sandbox_tenant_id),
            "archived_tenant_id": str(outcome.archived_tenant_id),
        },
    )


def _export_latest(jc: JobContext, snapshot_id: UUID, requester: UUID) -> None:
    """Capture fresh source inputs in the source tenant; the reset job stays in the sandbox."""
    from sqlalchemy import insert

    from erev_api.controls.release import current_release
    from erev_api.db.tables import tenant_snapshot
    from erev_api.domain.platform import snapshot_job as export
    from erev_api.domain.platform import snapshots
    from erev_api.enums import PrincipalKind, RunStatus

    known_at = jc.clock.now()
    with jc.unit_of_work() as uow:
        uow.session.execute(
            insert(tenant_snapshot).values(
                tenant_id=jc.tenant_id,
                id=snapshot_id,
                known_at=known_at,
                purpose="SANDBOX_SEED",
                status=RunStatus.QUEUED.value,
                job_id=None,
                created_at=uow.now,
                created_by=requester,
                created_by_kind=PrincipalKind.USER.value,
            )
        )
        uow.audit(
            action=snapshots.ACTION_REQUESTED,
            object_type="tenant_snapshot",
            object_id=snapshot_id,
            before=None,
            after={"status": RunStatus.QUEUED.value},
            detail={
                "known_at": known_at.isoformat(),
                "purpose": "SANDBOX_SEED",
                "sandbox_reset_job_id": str(jc.job_id),
                "requested_by": str(requester),
            },
        )
        uow.commit()
    try:
        with jc.unit_of_work() as uow:
            resolution = export.retention_policy_for(uow.session, known_at)
            reader = export.DbSnapshotReader(
                uow.principal.db_context,
                engine_release=export.engine_release_of(current_release()),
                retention=resolution.policy,
                retention_refusal=resolution.refusal,
                retention_unset=resolution.unset,
            )
            export.export_snapshot(
                export.DbSnapshotRepository(uow),
                reader,
                export.writer_for(uow),
                params=export.SnapshotParams(snapshot_id, known_at, "SANDBOX_SEED"),
                heartbeat=jc.heartbeat,
            )
            uow.commit()
    except Exception:
        # The source snapshot must not remain queued after a failed export.
        with jc.unit_of_work() as uow:
            export.fail_snapshot(
                export.DbSnapshotRepository(uow),
                snapshot_id,
                {"detail": "Latest-production sandbox refresh export failed."},
            )
            uow.commit()
        raise
