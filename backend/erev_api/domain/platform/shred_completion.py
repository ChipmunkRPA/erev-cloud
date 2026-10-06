"""SCH-16 ``file_shred_completion``: the sweep that finishes a decided shred nobody else finished
(05 §6.17 PRV-07 b and §7.4 OPR-24 rev 1.171; 04 T-PLT-29 rev 1.237; runbook RB-14; item
FILE-SHRED-DURABLE-ORDER-1).

A shred is decided in the command's transaction and its key is destroyed afterwards
(``domain.platform.privacy``, "Decide, then destroy"). The command's own continuation normally
does that before the request is answered, and ``file.shred`` sent again does it too. This is the
third road, for a row that neither reached: every 10 minutes, for every workspace, the rows whose
shred was decided at least ``GRACE`` ago and whose completion is not recorded — the grace leaves
the command's continuation its turn — are completed by ``privacy.complete_shred``, as SYSTEM, one
unit of work per file, at most ``BATCH`` files per workspace and run, oldest first. A file that
fails stays for the next run and does not hold the others back.

Only a key the workspace owns is finished here (05 SBX-08): a sandbox carries the rows of its
source with the source's keys, and a row that was decided there while the copy was taken is
finished in the source — the read here selects own keys only, and ``privacy.complete_shred``
refuses any other.

Rows shredded before revision 0120 carry no completion. The sweep finds their marker, deletes
nothing and records the completion with the marker's own instant: a revision cannot fill the
column, since it sees no tenant row (DG-MIG-13).

What fails is the store, its credentials or a lock — nothing a member of the workspace can
repair there. A row that is still not completed ``OVERDUE`` after its decision is therefore an
OPERATOR ALERT (``FILE_SHRED_INCOMPLETE``, WARNING, RB-14), values-free — the workspace, the
number of such files and the age of the oldest — and no exception item: that queue is the
accountants' work, and an item would name a file to people who may not know it exists. The alert
is raised by the run at the full hour, so an outage is told once an hour while it lasts and not
every ten minutes. What the workspace itself needs is on the row: ``shredded_at`` set,
``shred_completed_at`` empty, the content refused.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final
from uuid import UUID

from sqlalchemy import ColumnElement, func, select

from erev_api.auth.principal import system_principal
from erev_api.controls.operator_alerts import file_shred_incomplete_alert
from erev_api.db.session import platform_session, tenant_session
from erev_api.db.tables import file_object, tenant
from erev_api.domain.platform import privacy
from erev_api.jobs.context import JobRuntime, system_unit_of_work
from erev_api.logging import get_logger, register_logger_fields

__all__ = ["BATCH", "GRACE", "OVERDUE", "REQUEST_ID", "SweepResult", "run"]

# The command's own continuation has had its turn before the sweep takes a row.
GRACE: Final = timedelta(minutes=2)
# At most this many files per workspace and run, oldest decision first.
BATCH: Final = 200
# A decided shred still not completed after this long is told to the operators.
OVERDUE: Final = timedelta(minutes=60)
REQUEST_ID: Final = "file-shred-completion"
_LOGGER: Final = "erev_api.domain.platform.shred_completion"

register_logger_fields(
    _LOGGER,
    ("file_id", "road", "error_type", "workspaces", "completed", "failed", "overdue_workspaces"),
)


@dataclass(frozen=True, slots=True)
class SweepResult:
    """What one run did: the files it completed, the files that failed and stay for the next
    run, and the workspaces it raised the alert for."""

    completed: int
    failed: int
    alerted: tuple[UUID, ...]


def _owed(tenant_id: UUID, decided_before: datetime) -> ColumnElement[bool]:
    """Rows of the workspace decided before ``decided_before`` whose completion is not recorded,
    under a key the workspace owns (``ix_file_object__shred_incomplete`` bounds the scan)."""
    return (
        file_object.c.shredded_at.is_not(None)
        & file_object.c.shred_completed_at.is_(None)
        & (file_object.c.shredded_at <= decided_before)
        & file_object.c.storage_key.startswith(f"{tenant_id}/", autoescape=True)
    )


def run(runtime: JobRuntime, *, alert: bool) -> SweepResult:
    """The task body of SCH-16. ``alert`` is true for the run at the full hour: it also tells the
    operators of every workspace that holds a decided shred older than ``OVERDUE``."""
    files = runtime.files
    if files is None:
        raise RuntimeError("this job runtime has no file store")
    now = runtime.clock.now()
    log = get_logger(_LOGGER)
    with platform_session(
        "tenant_directory", actor_user_id=None, request_id=REQUEST_ID, keyring=runtime.keyring
    ) as db:
        tenant_ids = [
            UUID(str(value)) for value in db.scalars(select(tenant.c.id).order_by(tenant.c.id))
        ]
    completed = failed = 0
    alerted: list[UUID] = []
    for tenant_id in tenant_ids:
        principal = system_principal(tenant_id)
        with tenant_session(principal.db_context, read_only=True) as db:
            due = [
                UUID(str(value))
                for value in db.scalars(
                    select(file_object.c.id)
                    .where(_owed(tenant_id, now - GRACE))
                    .order_by(file_object.c.shredded_at, file_object.c.id)
                    .limit(BATCH)
                )
            ]
        for file_id in due:
            try:
                with system_unit_of_work(runtime, principal, request_id=REQUEST_ID) as uow:
                    finished = privacy.complete_shred(
                        uow, file_id, road=privacy.ROAD_SWEEP, files=files
                    )
                    uow.commit()
            except Exception as error:  # noqa: BLE001 — one file's failure holds no other back
                failed += 1
                log.warning(
                    "file_shred.completion_failed",
                    file_id=str(file_id),
                    road=privacy.ROAD_SWEEP,
                    error_type=type(error).__name__,
                )
                continue
            completed += int(finished is not None)
        # Nothing was owed past the grace, so nothing is overdue: the hourly question is asked
        # only of a workspace that had work in this run.
        if not alert or not due:
            continue
        with tenant_session(principal.db_context, read_only=True) as db:
            count, oldest = db.execute(
                select(func.count(), func.min(file_object.c.shredded_at)).where(
                    _owed(tenant_id, now - OVERDUE)
                )
            ).one()
        if not count:
            continue
        alerted.append(tenant_id)
        if runtime.alerts is not None:
            runtime.alerts.raise_alert(
                file_shred_incomplete_alert(
                    tenant_id=tenant_id,
                    files=int(count),
                    oldest_minutes=int((now - oldest).total_seconds() // 60),
                    raised_at=now,
                )
            )
    summary = {
        "workspaces": len(tenant_ids),
        "completed": completed,
        "failed": failed,
        "overdue_workspaces": len(alerted),
    }
    if failed or alerted:
        log.warning("file_shred_completion.completed", **summary)
    else:
        log.info("file_shred_completion.completed", **summary)
    return SweepResult(completed=completed, failed=failed, alerted=tuple(alerted))
