"""Impact preview snapshots (dev-guide §5.6 DG-KRN-APR-01; 04 T-PLT-17, E-68; REQ-PLT-015).

A preview is the canonical JSON of ``{"before": …, "after": …}`` (§5.17). Its SHA-256 is the
request's ``impact_preview_sha256`` and equals the ``sha256`` of the ``IMPACT_PREVIEW`` file that
stores the same bytes, so the stored snapshot proves what the approver saw. A subject without a
pending row of its own keeps its proposal as the ``after`` member (BUILD_SPEC BS1-D-24), which
``request_proposal`` reads back and verifies against the request's hash.

A subject whose own command retained its preview before the submission (a modification, 04
§16.14) hands that snapshot over instead (``retained_snapshot``; DG-KRN-APR-01 rev 1.75): the
request keeps the SAME file and hash, and the file's document carries ``before`` and ``after``
beside the subject's own members — one snapshot is what the preparer ran, what the request shows
and what the approver decides on.
"""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.canonical import canonical_bytes, sha256_hex
from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import approval_request, file_object
from erev_api.enums import FilePurpose
from erev_api.files.store import open_file, store_file

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.files.store import FileStore
    from erev_api.uow import UnitOfWork

MEDIA_TYPE: Final = "application/json"


def _document(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    return {"before": dict(before), "after": dict(after)}


def preview_sha256(before: Mapping[str, Any], after: Mapping[str, Any]) -> str:
    return sha256_hex(_document(before, after))


def store_preview(
    uow: UnitOfWork, *, before: Mapping[str, Any], after: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Store the snapshot as a file of purpose ``IMPACT_PREVIEW``; returns its ``file_object``."""
    return store_file(
        uow,
        purpose=FilePurpose.IMPACT_PREVIEW,
        stream=io.BytesIO(canonical_bytes(_document(before, after))),
        original_filename=None,
        media_type=MEDIA_TYPE,
    )


def retained_snapshot(session: Session, file_id: UUID, sha256: str) -> UUID:
    """The ``IMPACT_PREVIEW`` file a subject's command retained, verified as the request's
    snapshot: the row exists with that purpose and its ``sha256`` is the hash handed over (a
    mismatch is a programming error of the subject command, never a request naming bytes other
    than its hash)."""
    found = session.execute(
        select(file_object.c.purpose, file_object.c.sha256).where(file_object.c.id == file_id)
    ).one_or_none()
    if (
        found is None
        or str(getattr(found.purpose, "value", found.purpose)) != FilePurpose.IMPACT_PREVIEW.value
        or str(found.sha256) != sha256
    ):
        raise ValueError(f"file {file_id} is not the retained impact preview {sha256}")
    return file_id


def read_preview(
    session: Session, file_id: UUID, *, files: FileStore, keyring: KeyRing
) -> dict[str, Any]:
    """The stored ``{"before": …, "after": …}`` document of an ``IMPACT_PREVIEW`` file."""
    _, stream = open_file(session, file_id, files=files, keyring=keyring)
    with stream:
        document = json.loads(stream.read(), parse_float=Decimal)
    if not (
        isinstance(document, dict)
        and isinstance(document.get("before"), dict)
        and isinstance(document.get("after"), dict)
    ):
        raise LookupError(f"file {file_id} holds no impact preview")
    return document


def request_proposal(uow: UnitOfWork, approval_request_id: UUID) -> dict[str, Any]:
    """The ``after`` member of the request's stored preview, once the document matches the
    request's ``impact_preview_sha256`` (BS1-D-24)."""
    row = uow.session.execute(
        select(
            approval_request.c.impact_preview_file_id, approval_request.c.impact_preview_sha256
        ).where(approval_request.c.id == approval_request_id)
    ).one_or_none()
    if row is None or row.impact_preview_file_id is None:
        raise LookupError(f"approval request {approval_request_id} stores no proposal")
    document = read_preview(
        uow.session, row.impact_preview_file_id, files=uow.files, keyring=uow.keyring
    )
    if preview_sha256(document["before"], document["after"]) != row.impact_preview_sha256:
        raise LookupError(f"the preview of approval request {approval_request_id} changed")
    return dict(document["after"])
