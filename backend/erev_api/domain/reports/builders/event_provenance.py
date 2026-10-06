"""The recorder and the approval a register shows for a contract event (SCREENS_B §5.6.3 RPT-16
and RPT-17 "Recorded by", "Approval", rev 1.31; PRD J-04.5; 04 T-RPT-01 rule 4 rev 1.128,
T-CON-05, T-IMP-02; supervisor ruling R-63 (c)).

An event carries its own creator and its own approval request. An import commit appends its events
as the ``SYSTEM`` principal, and the control over them is the upload's ``IMPORT_COMMIT`` request
(T-IMP-02 ``approval_request_id``). So an event written by ``SYSTEM`` for an import —
``created_by_kind`` ``SYSTEM`` with an ``import_upload_id`` — is shown with the fields of its
upload: the uploader as the recorder and the upload's approval request. An event with no upload,
and an event a person or an API client recorded, keeps its own fields.

``resolved`` is pure over flat event records and the uploads ``uploads`` read, so the rule is
CPU-testable; both registers call them with the records they already hold, under the keys below.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import approval_request, import_upload
from erev_api.enums import PrincipalKind

# The keys of an event record: T-CON-05 ``created_by``, ``created_by_kind`` and
# ``import_upload_id``, and the ``request_no`` of the event's own approval request.
RECORDER: Final = "created_by"
RECORDER_KIND: Final = "created_by_kind"
APPROVAL: Final = "approval_request_no"
UPLOAD: Final = "import_upload_id"


@dataclass(frozen=True, slots=True)
class Upload:
    """What a register shows of an import upload (T-IMP-02): who uploaded it and the number of its
    ``IMPORT_COMMIT`` request, None for an upload that holds none."""

    created_by: UUID | None
    created_by_kind: str
    approval_request_no: str | None


def _kind(value: object) -> str:
    return str(getattr(value, "value", value))


def written_for_import(record: Mapping[str, Any]) -> bool:
    """Whether ``record`` is an event the ``SYSTEM`` principal wrote for an import upload."""
    return (
        record.get(UPLOAD) is not None
        and _kind(record.get(RECORDER_KIND)) == PrincipalKind.SYSTEM.value
    )


def resolved(
    records: Iterable[Mapping[str, Any]], uploads: Mapping[UUID, Upload]
) -> list[dict[str, Any]]:
    """Each record with the recorder and the approval a register shows: those of its upload for an
    event written by ``SYSTEM`` for an import whose upload is in ``uploads`` (the upload's request
    when it holds one, else the event's own), its own otherwise. Pure; the input is not changed."""
    found: list[dict[str, Any]] = []
    for record in records:
        shown = dict(record)
        upload = uploads.get(UUID(str(record[UPLOAD]))) if written_for_import(record) else None
        if upload is not None:
            shown[RECORDER] = upload.created_by
            shown[RECORDER_KIND] = upload.created_by_kind
            if upload.approval_request_no is not None:
                shown[APPROVAL] = upload.approval_request_no
        found.append(shown)
    return found


def uploads(session: Session, records: Iterable[Mapping[str, Any]]) -> dict[UUID, Upload]:
    """The uploads of the records written by ``SYSTEM`` for an import, by upload id."""
    ids = sorted(
        {UUID(str(record[UPLOAD])) for record in records if written_for_import(record)}, key=str
    )
    if not ids:
        return {}
    tenant_id = import_upload.c.tenant_id
    rows = session.execute(
        select(
            import_upload.c.id,
            import_upload.c.created_by,
            import_upload.c.created_by_kind,
            approval_request.c.request_no,
        )
        .select_from(
            import_upload.outerjoin(
                approval_request,
                and_(
                    approval_request.c.tenant_id == tenant_id,
                    approval_request.c.id == import_upload.c.approval_request_id,
                ),
            )
        )
        .where(import_upload.c.id.in_(ids))
    ).mappings()
    return {
        UUID(str(row["id"])): Upload(
            created_by=None if row["created_by"] is None else UUID(str(row["created_by"])),
            created_by_kind=_kind(row["created_by_kind"]),
            approval_request_no=None if row["request_no"] is None else str(row["request_no"]),
        )
        for row in rows
    }


def attributed(session: Session, records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """``resolved`` over the uploads the records name: one read, whatever their number."""
    held = [dict(record) for record in records]
    return resolved(held, uploads(session, held))
