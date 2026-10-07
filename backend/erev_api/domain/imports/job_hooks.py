"""What the failure hooks of the three import jobs share (05 §5.6 rev 1.185; 04 T-IMP-02 rev
1.270; PRD SM-05 rev 1.186; supervisor rulings R-108 (2) and R-105 (2) and the supervisor's
rulings of 2026-10-02).

One rule. A job that ends FAILED ends its upload when the upload is still in the state the job
found it in, or in the job's own state:

- ``IMPORT_VALIDATE`` — ``UPLOADED`` or ``VALIDATING`` → ``INVALID`` (``validate``);
- ``IMPORT_DIFF`` — ``VALIDATED`` or ``DIFFING`` → ``INVALID`` (``diff``);
- ``IMPORT_COMMIT`` — ``APPROVED`` or ``COMMITTING`` → ``FAILED`` (``commit``),

each with ``IMPORT_PROCESSING_FAILED`` under the job's reference. An import does not sit in a
state with a failed job behind it and nothing said, whether it has a way out or not: an upload
left ``APPROVED`` had none — it could be neither cancelled nor submitted again.

The hook runs in the transaction that ends the job (``jobs.registry._fail_job``), inside a
savepoint of the unit of work. Validation and diff skip held rows. Commit settlement waits
for a competing command, which may refuse without ending the upload. Since 05 JOB-06 rev 1.200
the holder is never the job's own work: no job is settled while its attempt has an open unit
of work.
"""

from __future__ import annotations

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import import_upload
from erev_api.enums import ImportStatus

__all__ = ["held_status"]


def held_status(
    session: Session, import_id: UUID, statuses: Collection[ImportStatus], *, wait: bool = False
) -> str | None:
    """The status of the upload, now locked by this transaction, when it is one of ``statuses``
    and its row could be locked (waiting only when requested). None otherwise: the upload
    has ended or moved on — the handler ended it, or its result was committed before the job
    failed — or, when ``wait`` is false, another transaction holds the row."""
    found = session.execute(
        select(import_upload.c.status)
        .where(
            import_upload.c.id == import_id,
            import_upload.c.status.in_([status.value for status in statuses]),
        )
        .with_for_update(skip_locked=not wait)
    ).scalar_one_or_none()
    return None if found is None else str(getattr(found, "value", found))
