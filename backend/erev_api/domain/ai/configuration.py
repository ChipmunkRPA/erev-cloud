"""Scope the administrator AI lifecycle to tenant AI versions, never accounting policies."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import registry_version
from erev_api.problems import Problem


def require_version(session: Session, version_id: UUID) -> None:
    """The caller's tenant RLS and the fixed category/scope are both required."""
    found = session.scalar(
        select(registry_version.c.id).where(
            registry_version.c.id == version_id,
            registry_version.c.category == "AI",
            registry_version.c.scope == "TENANT",
            registry_version.c.entity_id.is_(None),
            registry_version.c.book_code.is_(None),
        )
    )
    if found is None:
        raise Problem("not-found")
