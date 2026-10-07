"""Reviewed accounting evidence for an error-correction reopen (LIMITS B1-12).

The caller must hold the period state before binding this evidence. A nonblocking share lock
avoids reversing the judgement-review/group/period lock order: concurrent review is retryable,
not permission to accept a record whose status could change before the reopen commits.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from erev_api.approvals.subjects import judgement_record_content
from erev_api.db.tables import contract, judgement_record
from erev_api.problems import Problem, ProblemError


def reviewed_basis(
    session: Session,
    *,
    tenant_id: UUID,
    entity_id: UUID,
    book_code: str,
    judgement_id: UUID | None,
) -> dict[str, Any]:
    """Validate, hold and describe the reviewed judgement for a reopen's approval basis.

    An inaccessible, missing or wrong-entity record receives the same field error. The record
    must concern estimate versus error, be independently reviewed, and apply to this book.
    Its complete accounting content and review identity belong in the request's content hash.
    No inference from the conclusion text substitutes for the accountant's judgement.
    """
    if judgement_id is None:
        raise _invalid()
    statement = (
        select(judgement_record)
        .join(
            contract,
            (contract.c.tenant_id == judgement_record.c.tenant_id)
            & (contract.c.id == judgement_record.c.contract_id),
        )
        .where(
            judgement_record.c.tenant_id == tenant_id,
            judgement_record.c.id == judgement_id,
            contract.c.contracting_entity_id == entity_id,
        )
        .with_for_update(read=True, nowait=True, of=judgement_record)
    )
    try:
        with session.begin_nested():
            row = session.execute(statement).mappings().one_or_none()
    except DBAPIError as error:
        if getattr(error.orig, "sqlstate", None) != "55P03":
            raise
        raise Problem(
            "invalid-transition",
            "The judgement is being changed. Refresh it and retry the reopen request.",
        ) from error
    if row is None:
        raise _invalid()
    if (
        _text(row["topic"]) != "ESTIMATE_VS_ERROR"
        or _text(row["status"]) != "REVIEWED"
        or row["reviewer_id"] is None
        or row["reviewed_at"] is None
        or row["reviewer_id"] == row["created_by"]
        or (row["book_code"] is not None and _text(row["book_code"]) != book_code)
    ):
        raise _invalid()
    return {
        "id": str(judgement_id),
        "content": dict(judgement_record_content(session, judgement_id)),
        "reviewer_id": str(row["reviewer_id"]),
        "reviewed_at": row["reviewed_at"].isoformat(),
        "status": _text(row["status"]),
        "row_version": int(row["row_version"]),
    }


def _invalid() -> Problem:
    return Problem(
        "validation-failed",
        errors=[
            ProblemError(
                field="judgement_record_id",
                rule_id="REOPEN_REVIEWED_JUDGEMENT",
                message=(
                    "Select a reviewed estimate-versus-error judgement for a contract of this "
                    "entity and book. Complete its independent review before requesting reopen."
                ),
            )
        ],
    )


def _text(value: Any) -> str:
    return str(getattr(value, "value", value))
