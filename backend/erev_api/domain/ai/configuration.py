"""Scope the administrator AI lifecycle to tenant AI versions, never accounting policies."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from erev_api.db.tables import registry_version
from erev_api.enums import BookCode, RegistryCategory
from erev_api.problems import Problem
from erev_api.registry.platform import PLATFORM_PARAMETERS
from erev_api.registry.resolve import framework_default, resolve


def version_scope() -> tuple[ColumnElement[bool], ...]:
    """Fixed category and scope, applied in addition to the caller's tenant RLS."""
    return (
        registry_version.c.category == "AI",
        registry_version.c.scope == "TENANT",
        registry_version.c.entity_id.is_(None),
        registry_version.c.book_code.is_(None),
    )


def require_version(session: Session, version_id: UUID) -> None:
    """The caller's tenant RLS and the fixed category/scope are both required."""
    found = session.scalar(
        select(registry_version.c.id).where(
            registry_version.c.id == version_id,
            *version_scope(),
        )
    )
    if found is None:
        raise Problem("not-found")


def form_values(session: Session, *, known_at: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve the fixed tenant-AI catalogue; the caller cannot select accounting parameters."""
    specs = tuple(
        spec for spec in PLATFORM_PARAMETERS.values() if spec.category is RegistryCategory.AI
    )
    values = {
        spec.code: resolve(session, spec.code, book_code=BookCode.ASC606, known_at=known_at).value
        for spec in specs
    }
    defaults = {spec.code: framework_default(spec, BookCode.ASC606).value for spec in specs}
    return values, defaults
