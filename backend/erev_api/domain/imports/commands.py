"""Import commands: ``POST /imports/{id}/cancel`` (04 §16.6 import commands, E-40; PRD SM-05;
BUILD_SPEC DIN-1).

The uploader cancels an import in ``UPLOADED`` to ``DIFF_READY`` (SM-05); later states answer 409
``invalid-transition``, and another user 403 ``forbidden`` with a ``DENIED`` audit event — a user
who may read the upload: one whose ``contract.read`` scope does not cover it gets 404, as from the
import reads (supervisor ruling R-98 (8); 04 rev 1.147 §16.6). The upload row is locked first, so a
validation in progress finishes before the cancellation applies. ``submit`` and the commit belong
to DIN-3.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.audit import writer as audit_writer
from erev_api.db.tables import contract, import_row, import_upload, period_state
from erev_api.db.transitions import RULE_ID, apply
from erev_api.domain.imports import queries, scope
from erev_api.enums import BookCode, ImportStatus
from erev_api.periods import auto_approval_barred, posting_period
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.imports import ImportOut

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = ["CANCELLABLE", "cancel_import", "posts_into_closing_period"]

# BUILD_SPEC CLO-3: the row members that date a posting, and those that name its contract.
DATE_MEMBERS: Final = ("effective_date", "issue_date")
CONTRACT_MEMBERS: Final = ("contract",)
PARAMETER_DATE: Final = "effective_date"

OBJECT_TYPE: Final = "import_upload"
CANCEL_ACTION: Final = "import_upload.cancel"
CANCEL_PERMISSION: Final = "import.upload"
CANCELLABLE: Final = frozenset(
    {
        ImportStatus.UPLOADED.value,
        ImportStatus.VALIDATING.value,
        ImportStatus.VALIDATED.value,
        ImportStatus.DIFFING.value,
        ImportStatus.DIFF_READY.value,
    }
)
UPLOADER_DETAIL: Final = "Only the user who uploaded the file can cancel the import."


def cancel_import(uow: UnitOfWork, import_id: UUID) -> ImportOut:
    """Cancel an import before approval (E-40 ``CANCELLED``)."""
    session = uow.session
    row: Any = (
        session.execute(
            select(import_upload).where(import_upload.c.id == import_id).with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    principal = uow.principal
    # Supervisor ruling R-98 (8): an upload outside the caller's ``contract.read`` scope answers
    # as an unknown id, as the import reads do (04 API-R-43) — before the uploader check, whose
    # 403 and DENIED event would tell that the upload exists.
    scope.require_visible(principal, row)
    if row["created_by"] is None or row["created_by"] != principal.id:
        audit_writer.record_denied(
            uow.ctx,
            action=CANCEL_ACTION,
            object_type=OBJECT_TYPE,
            object_id=import_id,
            permission=CANCEL_PERMISSION,
            detail={"reason": "not the uploader"},
            keyring=uow.keyring,
        )
        raise Problem("forbidden", UPLOADER_DETAIL)
    status = str(row["status"])
    if status not in CANCELLABLE:
        message = f"An import in status {status} cannot be cancelled."
        raise Problem(
            "invalid-transition",
            message,
            errors=[ProblemError(field="status", rule_id=RULE_ID, message=message)],
        )
    apply(
        session,
        OBJECT_TYPE,
        import_id,
        to_status=ImportStatus.CANCELLED.value,
        set_values={
            "updated_at": uow.now,
            "updated_by": principal.id,
            "updated_by_kind": principal.kind.value,
        },
        expected_status=status,
    )
    uow.audit(
        action=CANCEL_ACTION,
        object_type=OBJECT_TYPE,
        object_id=import_id,
        before={"status": status},
        after={"status": ImportStatus.CANCELLED.value},
    )
    return queries.get_import(session, import_id)


def _as_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _entity_books(session: Session, entity_id: UUID) -> list[BookCode]:
    codes = session.execute(
        select(period_state.c.book_code).where(period_state.c.entity_id == entity_id).distinct()
    ).scalars()
    return sorted({BookCode(str(code)) for code in codes}, key=lambda member: member.value)


def posts_into_closing_period(session: Session, row: Mapping[str, Any]) -> bool:
    """PRD BR-DAT-07, BR-CLS-04 (REQ-CLS-003; BUILD_SPEC CLO-3) and BR-CLS-06 (REQ-CLS-011;
    BUILD_SPEC CLO-7): whether an import posts into a period in soft close or under reopen — its
    current lock record is a ``REOPEN``, also through the soft close that follows the reopen
    (``periods.auto_approval_barred``; supervisor ruling R-117 (c)) — where no auto-approval rule
    applies and a person other than the submitter decides.

    The dates are the upload parameter ``effective_date`` (legacy v1 templates) and the
    ``effective_date`` or ``issue_date`` members of the rows. A row naming an existing ``contract``
    posts for its contracting entity; any other date is checked for every entity with period states
    (fail closed, XR-12). Each (entity, date) maps to its posting period per kept book through
    DG-KRN-TIME-04; a date without a postable period posts nothing and does not count.
    """
    dated: dict[str, set[date]] = {}
    tenant_wide: set[date] = set()
    parameter = _as_date((row["parameters"] or {}).get(PARAMETER_DATE))
    if parameter is not None:
        tenant_wide.add(parameter)
    normalized_rows = session.execute(
        select(import_row.c.normalized).where(import_row.c.import_upload_id == row["id"])
    ).scalars()
    for values in normalized_rows:
        if not isinstance(values, Mapping):
            continue
        found = {_as_date(values.get(name)) for name in DATE_MEMBERS} - {None}
        dates = {value for value in found if value is not None}
        if not dates:
            continue
        named = next((str(values[name]) for name in CONTRACT_MEMBERS if values.get(name)), None)
        if named is None:
            tenant_wide |= dates
        else:
            dated.setdefault(named, set()).update(dates)
    targets: set[tuple[UUID, date]] = set()
    if dated:
        owners = session.execute(
            select(contract.c.external_id, contract.c.contracting_entity_id).where(
                contract.c.external_id.in_(sorted(dated))
            )
        ).tuples()
        for external_id, entity_id in owners:
            targets |= {(UUID(str(entity_id)), value) for value in dated[str(external_id)]}
    if tenant_wide:
        entity_ids = session.execute(select(period_state.c.entity_id).distinct()).scalars()
        targets |= {
            (UUID(str(entity_id)), value) for entity_id in entity_ids for value in tenant_wide
        }
    for entity_id, effective_date in sorted(targets, key=lambda item: (str(item[0]), item[1])):
        for book_code in _entity_books(session, entity_id):
            try:
                posting, _origin = posting_period(
                    session, entity_id=entity_id, book_code=book_code, effective_date=effective_date
                )
            except Problem:
                continue
            if auto_approval_barred(
                session, entity_id=entity_id, book_code=book_code, period_id=posting.id
            ):
                return True
    return False
